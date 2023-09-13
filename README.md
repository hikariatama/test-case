# [Backend] Test task

## Description

The example of interaction between 3 microservices: `sensor`, `manipulator` and `controller`.

# How to run

1. Clone the repository.
2. Run `cp .env.sample .env` and modify `.env` file if needed.
3. Run `docker-compose up --build -d`.
4. Navigate to http://127.0.0.1:4082 to see the API documentation for `controller` and try out various methods.

# Honorable mention

I am not familiar with MongoDB, but I used it anyway because of the speed it provides. This resulted in the bad implementation of aggregation in one of the parts of the `controller` service.