# up-db:
# 	docker compose up db -d

build:
	docker compose build


up-app:
	docker compose up --build --force-recreate web

bash-app:
	docker exec -it abwab-web-1 bash

migrate:
	docker exec -it abwab-web-1 sh -c "python manage.py makemigrations && python manage.py migrate"

run-tests:
	docker exec -it abwab-web-1 sh -c "python manage.py test"

coverage:
	docker exec -it abwab-web-1 sh -c "coverage run manage.py test && coverage report"

coverage-html:
	docker exec -it abwab-web-1 sh -c "coverage run manage.py test && coverage html"
# 	open in browser
	open htmlcov/index.html