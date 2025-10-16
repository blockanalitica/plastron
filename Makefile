format:
	ruff format . & ruff check --fix .


test_pg:
	DB_CONN="postgres://plastron:postgres@localhost:5400/plastron_db" pytest $(ARGS)
