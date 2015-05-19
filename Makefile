deps vendor_deps: check_setup
	npm install
	pip install --target=vendor -r requirements.txt

check_setup:
	@command -v npm > /dev/null || echo "missing dependencies: need to install npm"
	@command -v pip > /dev/null || echo "missing dependencies: need to install pip"
