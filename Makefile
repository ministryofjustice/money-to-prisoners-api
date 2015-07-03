run:
	boot2docker up
	eval "$(boot2docker shellinit)"
	docker-compose up

build:
	boot2docker up
	eval "$(boot2docker shellinit)"
	docker-compose build

.PHONY: run build
