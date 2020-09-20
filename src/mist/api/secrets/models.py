import logging
import mongoengine as me
from uuid import uuid4

from mist.api.users.models import Owner
from mist.api.ownership.mixins import OwnershipMixin
from mist.api.secrets import controllers


log = logging.getLogger(__name__)


class Secret(OwnershipMixin, me.Document):
    """ A Secret object """
    id = me.StringField(primary_key=True,
                        default=lambda: uuid4().hex)
    name = me.StringField(required=True)
    owner = me.ReferenceField(Owner, reverse_delete_rule=me.CASCADE)
    meta = {
        'allow_inheritance': True,
        'collection': 'secrets',
        'indexes': [
            {
                'fields': ['owner', 'name'],
                'sparse': False,
                'unique': True,
                'cls': False,
            },
        ],
    }

    _controller_cls = None

    def __init__(self, *args, **kwargs):
        super(Secret, self).__init__(*args, **kwargs)
        # Set attribute `ctl` to an instance of the appropriate controller.
        if self._controller_cls is None:
            raise NotImplementedError(
                "Can't initialize %s. Secret is an abstract base class and "
                "shouldn't be used to create cloud instances. All Secret "
                "subclasses should define a `_controller_cls` class attribute "
                "pointing to a `BaseSecretController` subclass." % self
            )
        elif not issubclass(self._controller_cls,
                            controllers.BaseSecretController):
            raise TypeError(
                "Can't initialize %s.  All Secret subclasses should define a"
                " `_controller_cls` class attribute pointing to a "
                "`BaseSecretController` subclass." % self
            )
        self.ctl = self._controller_cls(self)

        # Calculate and store key type specific fields.
        self._secret_specific_fields = [field for field in type(self)._fields
                                        if field not in Secret._fields]

    @property
    def data(self):
        raise NotImplementedError()

    def __str__(self):
        return '%s key %s (%s) of %s' % (type(self), self.name,
                                         self.id, self.owner)


class VaultSecret(Secret):
    """ A Vault Secret object """
    secret_engine_name = me.StringField(default='kv1')

    _controller_cls = controllers.VaultSecretController

    def __init__(self, name, key, value, secret_engine_name='kv1',
                 *args, **kwargs):
        """ Construct Secret object given Secret's path and key:value"""
        super(VaultSecret, self).__init__(*args, **kwargs)
        self.name = name
        self.secret_engine_name = secret_engine_name
        self.ctl.create_secret(key, value)

    @property
    def data(self):
        return self.ctl.read_secret()['data']


class SecretValue(me.Document):
    """ Retrieve the value of a Secret object """

    secret = me.ReferenceField(Secret, required=False)
    key_name = me.StringField()

    @property
    def value(self):
        if self.key_name:
            return self.secret.data[self.key_name]
        else:
            return self.secret.data
