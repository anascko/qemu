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
import tempfile
import netifaces
from avocado import skipUnless
from avocado_qemu import Test

from avocado.utils import network
from avocado.utils import wait
from avocado.utils.path import find_command
from avocado.utils import service
from avocado.utils import process


class Migration(Test):
    """
    :avocado: tags=migration
    """

    timeout = 10

    @staticmethod
    def migration_finished(vm):
        return vm.command('query-migrate')['status'] in ('completed', 'failed')

    def assert_migration(self, source_vm, dest_vm):
        wait.wait_for(self.migration_finished,
                      timeout=self.timeout,
                      step=0.1,
                      args=(source_vm,))
        self.assertEqual(source_vm.command('query-migrate')['status'], 'completed')
        self.assertEqual(dest_vm.command('query-migrate')['status'], 'completed')
        self.assertEqual(dest_vm.command('query-status')['status'], 'running')
        self.assertEqual(source_vm.command('query-status')['status'], 'postmigrate')

    def do_migrate(self, dest_uri, src_uri=None):
        dest_vm = self.get_vm('-incoming', dest_uri)
        dest_vm.add_args('-nodefaults')
        dest_vm.launch()
        if src_uri is None:
            src_uri = dest_uri
        source_vm = self.get_vm()
        source_vm.add_args('-nodefaults')
        source_vm.launch()
        source_vm.qmp('migrate', uri=src_uri)
        self.assert_migration(source_vm, dest_vm)

    def _get_free_port(self, address='localhost'):
        port = network.find_free_port()
        if port is None:
            self.cancel('Failed to find a free port')
        return port

    def _if_rdma_enable(self):
        rdma_stat = service.ServiceManager()
        rdma = rdma_stat.status('rdma')
        return rdma

    def _get_ip_rdma(self):
        get_ip_rdma = process.run('rdma link show').stdout.decode()
        for line in get_ip_rdma.split('\n'):
            if re.search(r"ACTIVE", line):
                interface = line.split(" ")[-2]
                ip = netifaces.ifaddresses(interface)[netifaces.AF_INET][0]['addr']
                return ip


    def test_migration_with_tcp_localhost(self):
        dest_uri = 'tcp:localhost:%u' % self._get_free_port()
        self.do_migrate(dest_uri)

    def test_migration_with_unix(self):
        with tempfile.TemporaryDirectory(prefix='socket_') as socket_path:
            dest_uri = 'unix:%s/qemu-test.sock' % socket_path
            self.do_migrate(dest_uri)

    @skipUnless(find_command('nc', default=False), "nc command not found on the system")
    def test_migration_with_exec(self):
        """
        The test works for both netcat-traditional and netcat-openbsd packages
        """
        free_port = self._get_free_port()
        dest_uri = 'exec:nc -l localhost %u' % free_port
        src_uri = 'exec:nc localhost %u' % free_port
        self.do_migrate(dest_uri, src_uri)

    @skipUnless(_if_rdma_enable(None), "Unit rdma.service could not be found")
    @skipUnless(_get_ip_rdma(None), 'RoCE(RDMA) service or interface not configured')
    def test_migration_with_rdma_localhost(self):
        ip = self._get_ip_rdma()
        free_port = self._get_free_port(address=ip)
        dest_uri = 'rdma:%s:%u' % (ip, free_port)
        self.do_migrate(dest_uri)
