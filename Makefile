.PHONY: test setup selftest
test:
	bash tests/smoke.sh

setup:
	bash scripts/setup.sh

selftest:
	bash scripts/selftest.sh
