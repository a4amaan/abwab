# up-db:
# 	docker compose up db -d

up-app:
	docker compose up --build --force-recreate web


bash-app:
	docker exec -it abwab-web-1 bash

migrate:
	docker exec -it abwab-web-1 sh -c "python manage.py makemigrations && python manage.py migrate"

run-tests:
	docker exec -it abwab-web-1 sh -c "python manage.py test"