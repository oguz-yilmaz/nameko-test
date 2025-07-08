import pika
import time

connection = pika.BlockingConnection(pika.ConnectionParameters('localhost'))
channel = connection.channel()
queue_name = 'my_queue'
channel.queue_declare(queue=queue_name)

# nameless exchange
# channel.basic_publish(exchange='', routing_key='my_queue', body='Hello, RabbitMQ!')

# === 1. Direct Exchange ===
# Behaviour: Routes messages to queues where the routing key matches exactly
# Example:
#       Queue bind key = "error"
#       Message key = "error" → Routed to queue
#       Message key = "info"  → Not routed
channel.exchange_declare(exchange='my_custom_exchange', exchange_type='direct')

channel.queue_declare(queue='direct_queue')
channel.queue_bind(exchange='my_custom_exchange', queue='direct_queue', routing_key='error')

channel.basic_publish(exchange='my_custom_exchange', routing_key='error', body='Direct: Error message')
# This message won't be routed to the 'direct_queue' since there is no binding for 'routing_key = info'
# We only have binding for 'routing_key = error'
channel.basic_publish(exchange='my_custom_exchange', routing_key='info', body='Direct: Info message')

# === 2. Fanout Exchange ===
# Behavior: Broadcasts messages to all bound queues, ignoring routing keys
channel.exchange_declare(exchange='events', exchange_type='fanout')

channel.queue_declare(queue='fanout_queue_1')
channel.queue_declare(queue='fanout_queue_2')

channel.queue_bind(exchange='events', queue='fanout_queue_1')
channel.queue_bind(exchange='events', queue='fanout_queue_2')

channel.basic_publish(exchange='events', routing_key='', body='Fanout: Broadcast message 1')
channel.basic_publish(exchange='events', routing_key='', body='Fanout: Broadcast message 2')
channel.basic_publish(exchange='events', routing_key='', body='Fanout: Broadcast message 3')

# === 3. Topic Exchange ===
# Behavior: Routes messages based on pattern matching using wildcards(optional):
#       * (matches one word)
#       # (matches zero or more words)
# Example:
#      Binding: logs.*
#      Message key: logs.info → Routed
#      Message key: logs.error.critical → Not routed
channel.exchange_declare(exchange='topic_logs', exchange_type='topic')

channel.queue_declare(queue='topic_queue_info')
channel.queue_declare(queue='topic_queue_all')

channel.queue_bind(exchange='topic_logs', queue='topic_queue_info', routing_key='logs.info')
channel.queue_bind(exchange='topic_logs', queue='topic_queue_all', routing_key='logs.#')

channel.basic_publish(exchange='topic_logs', routing_key='logs.info',
                      body='Topic: Info log')
channel.basic_publish(exchange='topic_logs', routing_key='logs.error.critical',
                      body='Topic: Critical error')

# === 4. Headers Exchange ===
# Behavior: Routes based on message header values, not routing keys
# Example: Route if header "format=pdf" and "type=report".
channel.exchange_declare(exchange='header_exchange', exchange_type='headers')

channel.queue_declare(queue='headers_queue')

channel.queue_bind(exchange='header_exchange', queue='headers_queue', 
                   arguments={'x-match': 'all', 'format': 'pdf', 'type': 'report'})

headers = {'format': 'pdf', 'type': 'report'}
properties = pika.BasicProperties(headers=headers)

channel.basic_publish(exchange='header_exchange', routing_key='', 
                      body='Headers: PDF Report', properties=properties)

print("All messages published.")

# To keep the connection open for a while to observe the Connection and the Channels tab
# in the RabbitMQ Web UI
time.sleep(10)
connection.close()
