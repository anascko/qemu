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

import array
import os
import tempfile
from socket import socketpair, fromfd, AF_UNIX, SOCK_STREAM, SCM_RIGHTS, SOL_SOCKET, CMSG_SPACE, CMSG_LEN
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

    def check_bin_path(cmd):
        try:
            find_command(cmd)
            return True
        except CmdNotFoundError:
            return False

    def _get_free_port(self):
        port = network.find_free_port()
        if port is None:
            self.cancel('Failed to find a free port')
        return port

# https://docs.python.org/3/library/socket.html#socket.socket.sendmsg
    def _send_fds(self, sock, msg, fds):
        return sock.sendmsg([msg], [(SOL_SOCKET, SCM_RIGHTS, array.array("i", fds))])

# https://docs.python.org/3/library/socket.html#socket.socket.recvmsg
    def _recv_fds(self, sock, msglen=8192, maxfds=4096):
        fds = array.array("i")
        msg, ancdata, flags, addr = sock.recvmsg(msglen, CMSG_LEN(maxfds * fds.itemsize))
        for cmsg_level, cmsg_type, cmsg_data in ancdata:
            if cmsg_level == SOL_SOCKET and cmsg_type == SCM_RIGHTS:
                fds.frombytes(cmsg_data[:len(cmsg_data) - (len(cmsg_data) % fds.itemsize)])
        return msg, list(fds)

    def test_migration_with_tcp_localhost(self):
        source_vm = self.get_vm()
        dest_uri = 'tcp:localhost:%u' % self._get_free_port()
        dest_vm = self.get_vm('-incoming', dest_uri)
        dest_vm.launch()
        source_vm.launch()
        source_vm.qmp('migrate', uri=dest_uri)
        self.assert_migration(source_vm, dest_vm)

    def test_migration_with_fd(self):
        opaque = 'fd-migration'
        dataToSend = b"{\"execute\": \"getfd\",  \"arguments\": {\"fdname\": \"fd-migration\"}}"
        sendSocket, recvSocket = socketpair(AF_UNIX, SOCK_STREAM)
        fd1 = sendSocket.fileno()
        fd2 = recvSocket.fileno()
        os.set_inheritable(fd1, True)
        os.set_inheritable(fd2, True)

        source_vm = self.get_vm()
        source_vm.launch()
        source_vm_fd = source_vm.get_sock_fd()
        sock_fd = fromfd(source_vm_fd, AF_UNIX, SOCK_STREAM)
        fdsToSend = [fd1, source_vm_fd]
        self._send_fds(sock_fd, dataToSend, fdsToSend)
        self._recv_fds(sock_fd)

        dest_vm = self.get_vm('-incoming', 'fd:%s' % fd2)
        dest_vm.launch()
        source_vm.qmp('migrate', uri='fd:%s' % opaque)
        self.assert_migration(source_vm, dest_vm)

    @skipUnless(check_bin_path('nc'), "nc command not found on the system")
    def test_migration_with_exec(self):
        free_port = self._get_free_port()
        dest_uri = 'exec:nc -l localhost %u' % free_port
        src_uri = "exec:nc localhost %u" % free_port
        source_vm = self.get_vm()
        source_vm.launch()
        dest_vm = self.get_vm('-incoming', dest_uri)
        dest_vm.launch()
        source_vm.qmp('migrate', uri=src_uri)
        self.assert_migration(source_vm, dest_vm)

    def test_migration_with_unix(self):
        source_vm = self.get_vm()
        source_vm.launch()
        with tempfile.TemporaryDirectory(prefix='socket_') as socket_path:
            dest_uri = 'unix:%s/qemu-test.sock' % socket_path
            dest_vm = self.get_vm('-incoming', dest_uri)
            dest_vm.launch()
            source_vm.qmp('migrate', uri=dest_uri)
            self.assert_migration(source_vm, dest_vm)

