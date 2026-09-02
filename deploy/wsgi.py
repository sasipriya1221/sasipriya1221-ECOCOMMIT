"""Production WSGI entrypoint for an operator-configured hosted deployment.

Importing this module validates the local deployment contract and constructs the
application. It does not start a listener or terminate TLS.
"""

from ecocommit.deployment import create_application_from_environment


application = create_application_from_environment()
