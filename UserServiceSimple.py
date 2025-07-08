from nameko.extensions import DependencyProvider

# First dependency provider
class DatabaseConnectionProvider(DependencyProvider):
    def setup(self):
        # Run once on service startup
        self.connection_pool = create_conntection_pool() # hypothetical func

    def get_dependency(self, worker_ctx):
        # worker_ctx is worker context object that Nameko provides which contains information
        # about the current worker and it's execution environment
        #
        # This runs for each worker - returning a different conntection for each
        self.connection_pool.acquire()

    def worker_teardown(self, worker_ctx):
        # Clean up the dependency after worker is done
        connection = worker_ctx.database # Access the injected db, e.g UserService.database
        self.connection_pool.release(connection)

# Second dependency provider
class RedisProvider(DependencyProvider):
    def setup(self):
        # run once on service startup
        self.redis_client = redis.Redis(host="localhost", port=6379)

    def get_dependency(self, worker_ctx):
        return self.redis_client



from nameko.rpc import rpc

class UserService:
    name = "user_service"

    # Declare the dependencies
    database = DatabaseConnectionProvider()
    cache = RedisProvider()

    @rpc
    def get_user(self, user_id):
        cached_user = self.cache.get(f"user:{user_id}")
        if cached_user:
            return cached_user

        # The database dependency is injected and available as delf.database
        user = self.database.query("SELECT * FROM users WHERE id = %s", (user_id,))

        return user
        # After this method competes, worker_teardown is called
        # and the database connection is released
