import mongoengine as me

from mist.api.users.models import User

class SCMToken(me.Document):
    # TODO(ce1109): OneToOne Foriegnkey
    user = me.ReferenceField(User, required=True, reverse_delete_rule=me.CASCADE)
    token = me.StringField(default='')

    def as_dict(self):
        """Returns the API representation of the `SCMToken` object."""
        return {
            'user': self.user.id,
            'token': self.token
        }

    meta = {
        'collection': 'scmtoken',
        'indexes': [
            {
                'fields': ['user'],
                'unique': True,
            }
        ]
    }
