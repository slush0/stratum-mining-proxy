stratum-mining-proxy
====================

Application providing bridge between old HTTP/getwork protocol and Stratum mining protocol.

Installation on Windows
-----------------------

1. Download official Windows binaries (EXE) from https://github.com/slush0/stratum-mining-proxy/downloads
2. Open downloaded file. It will open console window. Using default settings, proxy connects to Slush's pool interface
3. If you want to connect to another pool or change other proxy settings, type "mining_proxy.exe --help" in console window.

Installation on Linux
---------------------

1. Download TGZ file from https://github.com/slush0/stratum-mining-proxy/tarball/master
2. Unpack it by typing "tar xf slush0-stratum-mining_proxy*.tar.gz"
3. Most likely you already have Python installed on your system. Otherwise install it by "sudo apt-get install python-dev"
(on Ubuntu and Debian).
3. Type "sudo python setup.py install" in the unpacked directory.
4. You can start the proxy by typing "./mining_proxy.py" in the terminal window. Using default settings,
proxy connects to Slush's pool interface.
5. If you want to connect to another pool or change other proxy settings, type "mining_proxy.py --help".

Installation using Github
-------------------------

1. git clone git@github.com:slush0/stratum-mining-proxy.git
2. cd stratum-mining-proxy
3. sudo python setup.py develop ; This will install required dependencies (namely Twisted and Stratum libraries),
but don't install the package into the system.
4. You can start the proxy by typing "./mining_proxy.py" in the terminal window. Using default settings,
proxy connects to Slush's pool interface.
5. If you want to connect to another pool or change other proxy settings, type "./mining_proxy.py --help".
