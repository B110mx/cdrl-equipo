.PHONY: setup verify

setup:
    pip install -r requirements.txt

verify:
    python -m unittest discover -s tests -v
