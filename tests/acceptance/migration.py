# Migration test
#
# Copyright (c) 2019 Red Hat, Inc.
#
# Authors:
#  Cleber Rosa <crosa@redhat.com>
#  Caio Carrara <ccarrara@redhat.com>
#
# This work is licensed under the terms of the GNU GPL, version 2 or
# later.  See the COPYING file in the top-level directory.

import re
from avocado import skipUnless
from avocado_qemu import Test

from avocado.utils import network
from avocado.utils import wait
from avocado.utils import service
from avocado.utils import process
from avocado.utils.path import find_command, CmdNotFoundError


class Migration(Test):

    timeout = 10

    @staticmethod
    def migration_finished(vm):
        return vm.command('query-migrate')['status'] in ('completed', 'failed')

    def _get_free_port(self):
        port = network.find_free_port()
        if port is None:
            self.cancel('Failed to find a free port')
        return port

    def _if_rdma_enable(self):
        rdma_stat = service.ServiceManager()
        rdma = rdma_stat.status('rdma')
        return rdma

    def _get_ip_rdma(self):
        try:
            find_command('rxe_cfg')
        except CmdNotFoundError:
            return False
        rxe_run = process.run('rxe_cfg -l').stdout.decode()
        for line in rxe_run.split('\n'):
            if re.search(r"rxe[0-9]", line):
                ip = re.search(r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}", line).group()
                return ip

    def migration_process(self, dest_uri):
        source_vm = self.get_vm()
        dest_vm = self.get_vm('-incoming', dest_uri)
        dest_vm.launch()
        source_vm.launch()
        source_vm.qmp('migrate', uri=dest_uri)
        wait.wait_for(
            self.migration_finished,
            timeout=self.timeout,
            step=0.1,
            args=(source_vm,)
        )
        self.assertEqual(dest_vm.command('query-migrate')['status'], 'completed')
        self.assertEqual(source_vm.command('query-migrate')['status'], 'completed')
        self.assertEqual(dest_vm.command('query-status')['status'], 'running')
        self.assertEqual(source_vm.command('query-status')['status'], 'postmigrate')

    def test_migration_with_tcp_localhost(self):
        dest_uri = 'tcp:localhost:%u' % self._get_free_port()
        self.migration_process(dest_uri)

    @skipUnless(_if_rdma_enable)
    @skipUnless(_get_ip_rdma(None), 'RoCE(RDMA) service or interface not configured')
    def test_migration_with_rdma_localhost(self):
        dest_uri = 'rdma:%s:%u' % (self._get_ip_rdma(), self._get_free_port())
        self.migration_process(dest_uri)
