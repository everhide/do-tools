ENV = .venv
PYTHON = $(ENV)/bin/python3
PIP = $(ENV)/bin/pip

run: clean $(ENV)/bin/activate
	$(PIP) install --upgrade pip
	$(PIP) install wheel
	$(PIP) install piny
	$(PIP) install psycopg[binary]
	$(PIP) install -r requirements.txt
	python install.py

$(ENV)/bin/activate: requirements.txt
	python3 -m venv $(ENV)

clean:
	rm -rf __pycache__
	rm -rf $(ENV)
