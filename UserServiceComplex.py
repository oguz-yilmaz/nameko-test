# src/user_service/app/services/user_service.py
import uuid
import json
from datetime import datetime, timedelta
import newrelic.agent # For potential APM integration

from nameko.rpc import rpc, RpcProxy
from nameko.events import event_handler, EventDispatcher, SINGLETON, BROADCAST
from nameko.dependency_providers import Config
from nameko_redis import Redis
from nameko.extensions import DependencyProvider
from nameko.exceptions import RemoteError # For handling RPC call errors

# Assuming similar providers exist as in the 'dots' library
from dots.providers.logger_provider import LoggerProvider
from dots.providers.sequoia_metrics import SequoiaMetrics
from dots.exceptions import NotFound, BadRequest, Conflict

# --- Example Custom Dependency Provider (Simulated Database Interaction) ---
class DatabaseProvider(DependencyProvider):
    """
    A simulated dependency provider for database interactions.
    In a real service, this would use an ORM or a DB connection pool.
    """
    def __init__(self):
        self.users = {} # Using a simple dict to simulate a DB table
        print("DatabaseProvider initialized (simulated)")

    def get_user(self, user_id):
        print(f"Simulating DB get for user_id: {user_id}")
        return self.users.get(user_id)

    def create_user(self, user_id, data):
        print(f"Simulating DB create for user_id: {user_id}")
        self.users[user_id] = {**data, 'id': user_id, 'created_at': datetime.utcnow().isoformat()}
        return self.users[user_id]

    def update_user_status(self, user_id, status):
         print(f"Simulating DB update status for user_id: {user_id}")
         if user_id in self.users:
             self.users[user_id]['status'] = status
             self.users[user_id]['updated_at'] = datetime.utcnow().isoformat()
             return self.users[user_id]
         return None

    def delete_user(self, user_id):
         print(f"Simulating DB delete for user_id: {user_id}")
         if user_id in self.users:
             del self.users[user_id]
             return True
         return False

    def get_dependency(self, worker_ctx):
        # Return the provider instance itself or specific methods
        return self

# --- The Main User Service ---
class UserService:
    """
    Example User Service demonstrating various Nameko features.
    """
    # 1. Service Definition: Unique name for discovery and RPC targeting
    name = "user_service"

    # 2. Dependencies: Injected by Nameko framework
    log = LoggerProvider('user_service') # Custom logging provider
    config = Config() # Accesses config/app.yml
    redis = Redis('user_sessions') # Built-in Redis dependency, 'user_sessions' is the config key
    db = DatabaseProvider() # Our custom (simulated) database provider
    dispatch = EventDispatcher() # For publishing events
    notification_service = RpcProxy("sq_notification_service") # To call other services
    sequoia_metrics = SequoiaMetrics() # For custom metrics (optional)

    # --- Entrypoints ---

    # 3. RPC Entrypoint: Methods callable by other services
    @rpc
    @newrelic.agent.background_task() # Optional: New Relic monitoring
    def create_user(self, username: str, email: str, password: str):
        self.log.info(f"Attempting to create user: {username}")

        user_id = str(uuid.uuid4())
        user_data = {
            'username': username,
            'email': email,
            'status': 'active'
        }

        try:
            # Use the database dependency provider
            created_user = self.db.create_user(user_id, user_data)
            self.log.info(f"User created successfully: {user_id}")

            # 4. Event Publishing: Dispatch an event after creation
            event_payload = {
                "id": user_id,
                "username": username,
                "email": email,
                "created_at": created_user['created_at']
            }
            self.dispatch('user.created', event_payload)
            self.log.info(f"Dispatched 'user.created' event for {user_id}")

            return created_user

        except Conflict as e:
             self.log.warning(f"User creation conflict for {username}: {e}")
             raise # Re-raise the specific conflict
        except Exception as e:
            self.log.error(f"Failed to create user {username}: {e}", exc_info=True)
            raise GenericException(f"Could not create user: {e}") from e

    @rpc(expected_exceptions=(NotFound,)) # Declare expected exceptions
    @newrelic.agent.background_task()
    def get_user(self, user_id: str):
        """
        Retrieves user details by ID.
        - Attempts to fetch from Redis cache first.
        - Falls back to (simulated) database if not cached.
        - Caches result in Redis.
        """
        self.log.info(f"Attempting to get user: {user_id}")
        cache_key = f"user:{user_id}"

        # Check cache first
        cached_user = self.redis.get(cache_key)
        if cached_user:
            self.log.info(f"Cache hit for user: {user_id}")
            return json.loads(cached_user)

        self.log.info(f"Cache miss for user: {user_id}. Fetching from DB.")
        # Use the database dependency provider
        user = self.db.get_user(user_id)

        if user is None:
            self.log.warning(f"User not found: {user_id}")
            raise NotFound(f"User with ID {user_id} not found.")

        # Cache the result (expire after 1 hour)
        self.redis.set(cache_key, json.dumps(user), ex=3600)
        self.log.info(f"User fetched from DB and cached: {user_id}")
        return user

    @rpc
    @newrelic.agent.background_task()
    def delete_user(self, user_id: str):
        """
        Deletes a user.
        - Interacts with the (simulated) database.
        - Calls the NotificationService via RpcProxy.
        - Publishes a 'user.deleted' event.
        """
        self.log.info(f"Attempting to delete user: {user_id}")

        user = self.get_user(user_id) # Reuse get_user to ensure existence

        # Use the database dependency provider
        deleted = self.db.delete_user(user_id)

        if deleted:
            self.log.info(f"User deleted successfully from DB: {user_id}")

            # 5. RPC Call: Call another service
            try:
                self.notification_service.send_goodbye_email(user['email'], user['username'])
                self.log.info(f"Notified NotificationService about deletion of {user_id}")
            except RemoteError as e:
                # Log RPC errors but don't necessarily fail the whole operation
                self.log.error(f"Failed to call notification_service for user {user_id}: {e}")
            except Exception as e:
                 self.log.error(f"Unexpected error calling notification_service for user {user_id}: {e}", exc_info=True)


            # Publish event
            self.dispatch('user.deleted', {"id": user_id})
            self.log.info(f"Dispatched 'user.deleted' event for {user_id}")

            # Clear cache
            cache_key = f"user:{user_id}"
            self.redis.delete(cache_key)
            self.log.info(f"Cache cleared for user: {user_id}")

            return {"status": "deleted", "id": user_id}
        else:
            # This case shouldn't happen if get_user succeeded, but included for completeness
            self.log.error(f"Failed to delete user {user_id} from DB (already gone?)")
            raise NotFound(f"User with ID {user_id} could not be deleted (not found).")


    # 6. Event Handler Entrypoint: React to events from other services
    @event_handler("sq_subscription_service", "subscription.cancelled", handler_type=BROADCAST)
    @newrelic.agent.background_task()
    def handle_subscription_cancelled(self, payload):
        """
        Handles the event when a subscription is cancelled.
        Updates the user status in the (simulated) database.
        """
        user_id = payload.get("user_id")
        subscription_id = payload.get("subscription_id")
        self.log.info(f"Received subscription.cancelled event for user {user_id}, sub {subscription_id}")

        if not user_id:
            self.log.warning("Received subscription.cancelled event without user_id.")
            return

        # Use the database dependency provider
        updated_user = self.db.update_user_status(user_id, "inactive_subscription")

        if updated_user:
            self.log.info(f"Updated status for user {user_id} due to cancelled subscription {subscription_id}")
            # Optionally dispatch another event like 'user.status.updated'
            # self.dispatch('user.status.updated', updated_user)
        else:
             self.log.warning(f"Could not find user {user_id} to update status after subscription cancellation.")

    # 7. HTTP Entrypoint (less common in core services, often in gateways)
    # Usually requires a separate http runner or integrated setup.
    # For simplicity, we'll assume it's configured.
    # @http("GET", "/users/<user_id>") # Example route
    # def get_user_http(self, request, user_id):
    #     """ Exposes get_user via HTTP """
    #     try:
    #         user_data = self.get_user(user_id)
    #         return 200, json.dumps(user_data)
    #     except NotFound as e:
    #         return 404, json.dumps({"error": str(e)})
    #     except Exception as e:
    #         self.log.error(f"HTTP GET /users/{user_id} failed: {e}", exc_info=True)
    #         return 500, json.dumps({"error": "Internal server error"})


# --- Main file (e.g., src/main.py) ---
# import user_service.bootstrap # Run bootstrap first
# from user_service.app.services.user_service import UserService
# from user_service.app.services.metrics_service import MetricsService # Assuming metrics exists
