# A bug(?) in the configparser install means it does not set up backports/
# the way we need to, according to https://pypi.python.org/pypi/backports.
# We fix that manually.
deps vendor_deps: check_setup
	rm -r vendor/py2/* || true
	rm -r vendor/py3/* || true
	pip2 install --target=vendor/py2 -r requirements.txt
	pip3 install --target=vendor/py3 -r requirements.txt
	[ -d vendor/py2/backports ] && ! [ -s vendor/py2/backports/__init__.py ] && echo "from pkgutil import extend_path; __path__ = extend_path(__path__, __name__)" > vendor/py2/backports/__init__.py
	npm install
	npm update
	npm prune
	echo "DONE.  Consider running:  git add -A vendor node_modules"



check_setup:
	@command -v npm > /dev/null || echo "missing dependencies: need to install npm"
	@command -v pip2 > /dev/null || echo "missing dependencies: need to install pip2"
	@command -v pip3 > /dev/null || echo "missing dependencies: need to install pip3"
