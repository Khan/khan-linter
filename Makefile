# A bug(?) in the configparser install means it does not set up backports/
# the way we need to, according to https://pypi.python.org/pypi/backports.
# We fix that manually.
deps vendor_deps: go_deps check_setup
	rm -r vendor/py2/* || true
	rm -r vendor/py3/* || true
	pip3 install --target=vendor/py3 -r requirements.txt
	npm install
	npm update
	npm prune
	echo "DONE.  Consider running:  git add -A vendor node_modules"

# vendor in the deps for golangci-lint.
go_deps go_vendor_deps: check_setup
	if [ ! -e ./go.mod ]; then go mod init khan_linter; fi
	GO111MODULE=on go mod tidy
	GO111MODULE=on go mod vendor
	@# Go really wants to control the entire vendor directory, but we want to
	@# put other stuff there.  Revert that other stuff.
	@# TODO(benkraft): There's got to be a better way!
	git checkout vendor/ktlint* vendor/py*
	echo "DONE.  Consider running:  git add -A vendor"


check_setup:
	@command -v npm > /dev/null || echo "missing dependencies: need to install npm"
	@command -v pip2 > /dev/null || echo "missing dependencies: need to install pip2"
	@command -v pip3 > /dev/null || echo "missing dependencies: need to install pip3"
