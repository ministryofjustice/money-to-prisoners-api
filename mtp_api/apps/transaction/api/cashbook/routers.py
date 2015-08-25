from rest_framework.routers import DefaultRouter, Route


class TransactionRouter(DefaultRouter):

    def get_routes(self, viewset):
        simple_routes = super(TransactionRouter, self).get_routes(viewset)
        extra_routes = [
            Route(
                url=r'^{prefix}/(?P<prison_id>\w+){trailing_slash}$',
                mapping={'get': 'list'},
                initkwargs={'suffix': 'List'},
                name='{basename}-prison-list'
            ),
            Route(
                url=r'^{prefix}/(?P<prison_id>\w+)/(?P<user_id>[0-9]+){trailing_slash}$',
                mapping={
                    'get': 'list',
                    'patch': 'patch_credited'
                },
                initkwargs={'suffix': 'List'},
                name='{basename}-prison-user-list'
            ),
            Route(
                url=r'^{prefix}/(?P<prison_id>\w+)/(?P<user_id>[0-9]+)/lock{trailing_slash}$',
                mapping={'post': 'lock'},
                initkwargs={'suffix': 'Lock'},
                name='{basename}-prison-user-lock'
            ),
            Route(
                url=r'^{prefix}/(?P<prison_id>\w+)/(?P<user_id>[0-9]+)/unlock{trailing_slash}$',
                mapping={'post': 'unlock'},
                initkwargs={'suffix': 'Unlock'},
                name='{basename}-prison-user-unlock'
            ),
        ]

        return extra_routes + simple_routes
