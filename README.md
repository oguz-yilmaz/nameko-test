# nameko

## Start the virtual env

```bash
# if you did not create a virtual env yet
$ python -m venv .venv

$ source .venv/bin/activate
```

## Start a RabbitMQ

```bash
# first time
docker run -d --name rabbitmq -p 5672:5672 -p 15672:15672 rabbitmq:3-management

# later
docker start rabbitmq
```

## Ports

`-d`: start it as deamon, will run RabbitMQ on background

`-p 5672:5672`: Maps port 5672 from the container to port 5672 on your host
machine (this is RabbitMQ's default AMQP port)

`-p 15672:15672`: Access the RabbitMQ management via port 15672 on localhost

## Start nameko service

You use Nameko runner executable to start a server

```bash
# Start the server and it keeps running and listens for events from the EventBus(RabbitMQ queue)
$ nameko run helloworld
starting services: greeting_service
Connected to amqp://guest:**@127.0.0.1:5672//
```

# A Nameko Service

- A fundamental unit in Nameko is a Service
- A service is typically a Python class that inherits from `nameko.rpc.Service`

```py
# A nameko service
class SqAuthService:
    name = "sq_auth_service"
    # ... other attributes and methods
```

**1. Entrypoints**

Methods within service class become entrypoints using specific decorators

- `@rpc:` Exposes a method for RPC from other services
- `@event_handler("source_service_name", "event_type"):` Makes a method listen
for specific events published by other services(or itself)
- `@http("METHOD", "/url/path"):` Exposes a method as an HTTP endpoint (User in gateway services or for metrics/health checks)
- `@timer(interval_seconds):` Defines a method that runs periadically at a specified interval
- `@websocket_rpc:` Exposes methods over Websockets
- `@consume(...):` For more direct interaction with message queues (e.g AMQP)

**2. Dependencies (`nameko.extensions.DependencyProvider`)**

`Dependencies` are class attributes within a `Service` class that provide access to external resources or other
services

- Common Built-in Dependencies:
-- `RpcProxy("target_service_name")`: Provides a proxy object to make RPC calls
to another Nameko service
-- `EventDispatcher()`: Provides an object to dispatch events that other
services(or itself) can listen to
-- `Config()`: Injects configuration values defined in a `config.yaml` file

- Custom: You can defines custom dependency providers, for databases, caching,
external APIs, etc

**3. Communication**

- `RPC (Remote Procedure Call):` Synchronous-style request/response
communication. A service calls a method on another service and waits for the
result. Under the hood, this usually uses AMQP request-response patterns.

- `Events (Publish/Subscribe):` Asynchronous, decoupled communication. A service
dispatches an event (fires and forgets), and any number of other services
subscribed to that event type will react.

**4. Message Broker (RabbitMQ):**

- Nameko heavily relies on a message broker, with RabbitMQ being the default
and most well-supported.
- The `AMQP_URI` in the configuration tells Nameko how to connect to RabbitMQ.

**Configuration (config.yaml):**
- Services are typically configured via a YAML file.
- This includes the `AMQP_URI`, database connection strings, logging settings,
and custom service-specific parameters.
- The `Config()` dependency provider makes these values accessible within your
service.

**5. Concurrency (`eventlet`):**

- Nameko uses `eventlet` for cooperative multitasking (`'green threads'`). This
allows a single process to handle many concurrent requests/tasks efficiently
without the overhead of OS threads or complex async/await syntax.
- Most I/O operations (network calls, database queries with compatible drivers)
are non-blocking.

**6. Runner (`$ nameko run`):**

- The command-line tool used to start and manage Nameko services.
- `$ nameko run my_service_module --config my_config.yaml`

**7. Shell (`$ nameko shell`):**

- An interactive Python shell that connects to a running Nameko cluster.
- Incredibly useful for debugging, manually triggering RPC calls, or
dispatching events.


.........................

# A microservice that has multiple nameko service

When you have multiple Nameko services that logically belong together, you can
group them into a larger microservice component.

## Example microservice: Math Micrservice

### Project Folder Structure

```txt
math_microservice/
├── __init__.py                     # empyt, Makes 'math_microservice' a Python package
├── config.yaml                     # Configuration for all services
├── main.py                         # IMPORTANT!: The entrypoint that imports all service classes
└── services/                       # Directory for individual service modules
    ├── __init__.py                 # Makes 'services' a Python sub-package
    ├── math_service.py
    └── reporting_service.py
README.md                           # Instructions (like this explanation)
```

### File Contents

**1. `math_microservice/config.yaml`**

```yaml
AMQP_URI: 'pyamqp://guest:guest@localhost'
WEB_SERVER_ADDRESS: '0.0.0.0:8001' # Port for HTTP endpoints

# Optional: service-specific configuration
# Service names must match
MAX_WORKERS:
  math_service: 5 # name = "math_service"
  reporting_service: 10 # name = "reporting_service"
```

**1. `math_microservice/services/math_service.py`**

```py
from nameko.rpc import rpc, Service
from nameko.events import event_handler

class MathService:
    name = "math_service"

    @rpc
    def add(self, x, y):
        return x + y

    @rpc
    def multiply(self, x, y):
        return x * y

    @event_handler("reporting_service", "calcuation_requested")
    def log_calculation_requested(self, payload):
        # do something with this requested calculation
```

**2. `math_microservice/services/reporting_service.py`**

```py
from nameko.rpc import rpc, RpcProxy
from nameko.web.handlers import http
from nameko.events import EventDispatcher

class ReportingService:
    name = "reporting_service"

    math_service_rpc = RpcProxy("math_service") # Dependency provider to call MathService methods
    event_dispatcher = EventDispatcher()

    @http("GET", "/math/add/<int:x>/<int:y>")
    def http_add(self, request, x, y):
        # dispatch "calculate_requested" event to the queue
        self.event_dispatcher("calculate_requested", {"Operation": "add", "operands": [x, y]})
        sum_result = self.math_service_rpc.add(x, y)

        return (200, json.dumps({"result": sum_result}))


    @http("GET", "/math/multiply/<int:x>/<int:y>")
    def http_multiply(self, request, x, y):
        # dispatch "calculate_requested" event to the queue
        self.event_dispatcher("calculate_requested", {"Operation": "multiply", "operands": [x, y]})
        sum_result = self.math_service_rpc.multiply(x, y)

        return (200, json.dumps({"result": sum_result}))

    @rpc
    def generate_report(self, a, b):
        sum_val = self.math_rpc.add(a, b)
        prod_val = self.math_rpc.multiply(a, b)
        report = f"Report for numbers {a} and {b}: Sum={sum_val}, Product={prod_val}"

        self.event_dispatcher("report_generated", {"report_summary": f"Sum {sum_val}, Prod {prod_val}"})

        return report
```

**3. `math_microservice/main.py`**

```py
# math_microservice/main.py

# Assuming you run `nameko run math_microservices.main` from the directory
# containing the `math_microservice` folder
from math_microservice.services.math_service import MathService
from math_microservice.services.reporting_service import ReportingService

# No other Nameko-specific code needed in this main.py file
```

### How to run

**1. Prerequisites:**

- Install nameko: `pip install nameko "nameko[http,rpc,events]"`
- Have RabbitMQ running: `docker run -d --rm -p 5672:5672` -p 15672:15672 --name nameko_rabbitmq rabbitmq:3-management``

**2. Navigote to the Correct Directory:**

- Go to the directory that contains the `math_microservice` folder

**3. Run Nameko**

```bash
$ nameko run math_microservice.main --config math_microservice/config.yaml
```

You should see logs indicating that both `MathService` and `ReportingService`
are starting up, connecting to RabbitMQ, and the HTTP server is listening on
port 8001

### How to test

**1. Test HTTP Endpoints**

```bash
$ curl http://localhost:8001/math/add/10/5
$ curl http://localhost:8001/math/multiply/10/5
```

**2. Test RPC(using `nameko shell`)**

- Start nameko shell
```bash
$ nameko shell
```

- Inside shell
-- Call `MathService` directly:
    ```py
    n.rpc.math_service.add(100, 200)
    # Output: 300

    n.rpc.math_service.multiply(5, 5)
    # Output: 25
    ```
-- Call `ReportingService` RPC, which in turns calls MathService:
    ```py
    n.rpc.reporting_service.generate_report(a=4, b=6)
    ```

### Under the hood

When you execute nameko run <module_path> --config <config_file>:

**1. Discovery:** Nameko inspects the Python module you specified (e.g.,
math_microservice.main). It looks for all classes defined or imported into that
module that are Nameko service classes (i.e., they inherit from
nameko.Service).

**2. Worker Pools for EACH Service:** For each distinct service class it finds
(e.g., MathService, ReportingService):
- Nameko creates and starts a pool of worker instances.
- Each worker is an actual instance of your service class, running in its own
lightweight "green thread" (managed by eventlet).
- These workers are what actually execute your service methods when an
entrypoint (like an RPC call, an HTTP request, or an event) is triggered for
that specific service.

**3. Concurrency:**
- Having multiple workers per service allows that service to handle multiple
requests or events concurrently. For example, if 10 RPC calls arrive for
MathService simultaneously, up to 10 MathService workers can process them in
parallel (if you have at least 10 workers configured for MathService).
- The number of workers per service is configurable (default is often 10, but
can be set in config.yaml).
