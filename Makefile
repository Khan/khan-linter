deps vendor_deps: check_setup
	pip install --target=vendor -r requirements.txt
	npm install
	npm update
	npm prune
	echo "DONE.  Consider running:  git add -A vendor node_modules"

check_setup:
	@command -v npm > /dev/null || echo "missing dependencies: need to install npm"
	@command -v pip > /dev/null || echo "missing dependencies: need to install pip"
