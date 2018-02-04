image:
	docker build -t khanacademy/khan-linter .

deploy: image
	docker push khanacademy/khan-linter

deps vendor_deps: check_setup
	rm -r vendor/py2/* || true
	rm -r vendor/py3/* || true
	pip2 install --target=vendor/py2 -r requirements.txt
	pip3 install --target=vendor/py3 -r requirements.txt
	npm install
	npm update
	npm prune
	echo "DONE.  Consider running:  git add -A vendor node_modules"

check_setup:
	@command -v npm > /dev/null || echo "missing dependencies: need to install npm"
	@command -v pip2 > /dev/null || echo "missing dependencies: need to install pip2"
	@command -v pip3 > /dev/null || echo "missing dependencies: need to install pip3"
