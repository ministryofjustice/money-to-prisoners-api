from rest_framework.routers import DefaultRouter, Route


class CashbookTransactionRouter(DefaultRouter):

    def get_routes(self, viewset):
        simple_routes = super(CashbookTransactionRouter, self).get_routes(viewset)
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
                url=r'^{prefix}/(?P<prison_id>\w+)/(?P<user_id>[0-9]+)/take{trailing_slash}$',
                mapping={'post': 'take'},
                initkwargs={'suffix': 'Take'},
                name='{basename}-prison-user-take'
            ),
            Route(
                url=r'^{prefix}/(?P<prison_id>\w+)/(?P<user_id>[0-9]+)/release{trailing_slash}$',
                mapping={'post': 'release'},
                initkwargs={'suffix': 'Release'},
                name='{basename}-prison-user-release'
            ),
        ]

        return extra_routes + simple_routes
