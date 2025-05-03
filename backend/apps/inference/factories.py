import factory
from factory.django import DjangoModelFactory
from django.contrib.auth import get_user_model
from .models import InferenceRequest

User = get_user_model()


class InferenceRequestFactory(DjangoModelFactory):
    class Meta:
        model = InferenceRequest

    user = factory.SubFactory("apps.accounts.factories.UserFactory")
    inference_type = factory.Iterator(
        [choice[0] for choice in InferenceRequest.INFERENCE_TYPES]
    )
    payload = factory.Dict(
        {
            "prompt": factory.Faker("sentence", nb_words=10),
            "temperature": factory.Faker("pyfloat", min_value=0.0, max_value=2.0),
            "max_tokens": factory.Faker("pyint", min_value=100, max_value=2000),
        }
    )
    status = factory.Iterator([choice[0] for choice in InferenceRequest.STATUS_CHOICES])
    results = factory.Dict(
        {
            "text": factory.Faker("paragraph"),
            "tokens_used": factory.Faker("pyint", min_value=50, max_value=1000),
        }
    )
