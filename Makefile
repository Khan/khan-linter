deps install_deps: check_setup
	npm install

check_setup:
	@command -v npm > /dev/null || echo "missing dependencies: need to install npm"

post_pull: install_deps ;
