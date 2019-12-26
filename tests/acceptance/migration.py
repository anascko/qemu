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


from avocado_qemu import Test
from avocado import skipUnless
from avocado.utils import network
from avocado.utils import wait
from avocado.utils.path import find_command, CmdNotFoundError

class Migration(Test):

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

    def _get_free_port(self):
        port = network.find_free_port()
        if port is None:
            self.cancel('Failed to find a free port')
        return port

    def test_migration_with_tcp_localhost(self):
        source_vm = self.get_vm()
        dest_uri = 'tcp:localhost:%u' % self._get_free_port()
        dest_vm = self.get_vm('-incoming', dest_uri)
        dest_vm.launch()
        source_vm.launch()
        source_vm.qmp('migrate', uri=dest_uri)
        self.assert_migration(source_vm, dest_vm)

    @skipUnless(find_command('nc', default=False), "nc command not found on the system")
    def test_migration_with_exec(self):
        free_port = self._get_free_port()
        source_vm = self.get_vm()
        dest_uri = 'exec:nc -l localhost %u' % free_port
        src_uri = 'exec:nc localhost %u' % free_port
        source_vm.launch()
        dest_vm = self.get_vm('-incoming', dest_uri)
        dest_vm.launch()
        source_vm.qmp('migrate', uri=src_uri)
        self.assert_migration(source_vm, dest_vm)
