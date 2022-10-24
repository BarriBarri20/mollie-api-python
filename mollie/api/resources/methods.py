from ..objects.list import ObjectList
from ..objects.method import Method
from .base import ResourceBase, ResourceGetMixin, ResourceListMixin


class Methods(ResourceBase, ResourceGetMixin, ResourceListMixin):
    def get_resource_object(self, result):
        return Method(result, self.client)

    def all(self, **params):
        """List all mollie payment methods, including methods that aren't activated in your profile."""
        path = "methods/all"
        result = self.perform_api_call(self.REST_LIST, path, params=params)
        return ObjectList(result, self.get_resource_object({}).__class__, self.client)
