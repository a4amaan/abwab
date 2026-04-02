import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from accounts.models import Transaction
from accounts.publisher import EventPublisher

logger = logging.getLogger(__name__)

publisher = EventPublisher()


@receiver(post_save, sender=Transaction)
def send_transaction_to_kafka(sender, instance, created, **kwargs):
    if not created:
        # Only emit for new transactions (you can also emit on update)
        return

    event_data = {
        'transaction_id': instance.id,
        'account_id': instance.account_id,
        'type': instance.type,
        'amount': str(instance.amount),
        'created_at': instance.created_at.isoformat(),
        'description': instance.description,
        'idempotency_key': instance.idempotency_key,
    }
    publisher.publish(instance.type, event_data)
