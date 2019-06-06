import json
import platform
import re
import ssl
import warnings
from collections import OrderedDict

import requests

from .error import RequestError, RequestSetupError
from .resources.captures import Captures
from .resources.chargebacks import Chargebacks
from .resources.customer_mandates import CustomerMandates
from .resources.customer_payments import CustomerPayments
from .resources.customer_subscriptions import CustomerSubscriptions
from .resources.customers import Customers
from .resources.invoices import Invoices
from .resources.methods import Methods
from .resources.onboarding import Onboarding
from .resources.orders import Orders
from .resources.organizations import Organizations
from .resources.payment_chargebacks import PaymentChargebacks
from .resources.payment_refunds import PaymentRefunds
from .resources.payments import Payments
from .resources.permissions import Permissions
from .resources.profile_chargebacks import ProfileChargebacks
from .resources.profile_methods import ProfileMethods
from .resources.profile_payments import ProfilePayments
from .resources.profile_refunds import ProfileRefunds
from .resources.profiles import Profiles
from .resources.refunds import Refunds
from .resources.subscription_payments import SubscriptionPayments
from .version import VERSION

try:
    from urllib.parse import urlencode
except ImportError:
    # support python 2
    from urllib import urlencode


class Client(object):
    CLIENT_VERSION = VERSION
    API_ENDPOINT = 'https://api.mollie.com'
    API_VERSION = 'v2'
    UNAME = ' '.join(platform.uname())

    @staticmethod
    def validate_api_endpoint(api_endpoint):
        return api_endpoint.strip().rstrip('/')

    @staticmethod
    def validate_api_key(api_key):
        api_key = api_key.strip()
        if not re.compile(r'^(live|test)_\w+$').match(api_key):
            raise RequestSetupError(
                "Invalid API key: '{api_key}'. An API key must start with 'test_' or 'live_'.".format(api_key=api_key))
        return api_key

    @staticmethod
    def validate_access_token(access_token):
        access_token = access_token.strip()
        if not access_token.startswith('access_'):
            raise RequestSetupError(
                "Invalid access token: '{access_token}'. An access token must start with 'access_'.".format(
                    access_token=access_token))
        return access_token

    def __init__(self, api_key=None, api_endpoint=None, timeout=10):
        self.api_endpoint = self.validate_api_endpoint(api_endpoint or self.API_ENDPOINT)
        self.api_version = self.API_VERSION
        self.timeout = timeout
        self.api_key = None

        self.oauth = None
        self.client_secret = None
        self.access_token = None

        # add endpoint resources
        self.payments = Payments(self)
        self.payment_refunds = PaymentRefunds(self)
        self.payment_chargebacks = PaymentChargebacks(self)
        self.profiles = Profiles(self)
        self.profile_chargebacks = ProfileChargebacks(self)
        self.profile_methods = ProfileMethods(self)
        self.profile_payments = ProfilePayments(self)
        self.profile_refunds = ProfileRefunds(self)
        self.methods = Methods(self)
        self.refunds = Refunds(self)
        self.chargebacks = Chargebacks(self)
        self.customers = Customers(self)
        self.customer_mandates = CustomerMandates(self)
        self.customer_subscriptions = CustomerSubscriptions(self)
        self.customer_payments = CustomerPayments(self)
        self.orders = Orders(self)
        self.organizations = Organizations(self)
        self.subscription_payments = SubscriptionPayments(self)
        self.invoices = Invoices(self)
        self.permissions = Permissions(self)
        self.onboarding = Onboarding(self)
        self.captures = Captures(self)
        # compose base user agent string
        self.user_agent_components = OrderedDict()
        self.set_user_agent_component('Mollie', self.CLIENT_VERSION)
        self.set_user_agent_component('Python', platform.python_version())
        self.set_user_agent_component('OpenSSL', ssl.OPENSSL_VERSION.split(' ')[1],
                                      sanitize=False)  # keep legacy formatting of this component

        if api_key:
            # There is no clean way for supporting both API key and access token acceptance and validation
            #  in __init__(). Furthermore the naming of the parameter would be inconsistent.
            # Using class methods is way cleaner.
            #
            # Warning added in 2.1.1, remove support in 2.3.x or so.
            msg = "Setting the API key during init will be removed in the future. " \
                  "Use Client.set_api_key() or Client.set_access_token() instead."
            warnings.warn(msg, PendingDeprecationWarning)
            self.api_key = self.validate_api_key(api_key)

    def set_api_endpoint(self, api_endpoint):
        self.api_endpoint = self.validate_api_endpoint(api_endpoint)

    def set_api_key(self, api_key):
        self.api_key = self.validate_api_key(api_key)

    def set_access_token(self, access_token):
        self.api_key = self.validate_access_token(access_token)
        self.set_user_agent_component('OAuth', '2.0', sanitize=False)  # keep spelling equal to the PHP client

    def set_timeout(self, timeout):
        self.timeout = timeout

    def set_user_agent_component(self, key, value, sanitize=True):
        """Add or replace new user-agent component strings.

        Given strings are formatted along the format agreed upon by Mollie and implementers:
        - key and values are separated by a forward slash ("/").
        - multiple key/values are separated by a space.
        - keys are camel-cased, and cannot contain spaces.
        - values cannot contain spaces.

        Note: When you set sanitize=false yuu need to make sure the formatting is correct yourself.
        """
        if sanitize:
            key = ''.join(_x.capitalize() for _x in re.findall(r'\S+', key))
            if re.search(r'\s+', value):
                value = '_'.join(re.findall(r'\S+', value))
        self.user_agent_components[key] = value

    @property
    def user_agent(self):
        """Return the formatted user agent string."""
        components = ["/".join(x) for x in self.user_agent_components.items()]
        return " ".join(components)

    def perform_http_call(self, http_method, path, data=None, params=None):
        if not self.oauth and not self.api_key:
            raise RequestSetupError('You have not set an API key. Please use set_api_key() to set the API key.')
        if path.startswith('%s/%s' % (self.api_endpoint, self.api_version)):
            url = path
        else:
            url = '%s/%s/%s' % (self.api_endpoint, self.api_version, path)

        if data is not None:
            try:
                data = json.dumps(data)
            except Exception as err:
                raise RequestSetupError("Error encoding parameters into JSON: '{error}'.".format(error=err))

        querystring = generate_querystring(params)
        if querystring:
            url += '?' + querystring
            params = None

        if self.oauth:
            try:
                response = self.oauth.request(
                    http_method,
                    url,
                    params=params,
                    data=data,
                )
            except Exception as err:
                raise RequestError('Unable to communicate with Mollie: {error}'.format(error=err))
        else:
            try:
                response = requests.request(
                    http_method, url,
                    verify=True,
                    headers={
                        'Accept': 'application/json',
                        'Authorization': 'Bearer {api_key}'.format(api_key=self.api_key),
                        'Content-Type': 'application/json',
                        'User-Agent': self.user_agent,
                        'X-Mollie-Client-Info': self.UNAME,
                    },
                    params=params,
                    data=data,
                    timeout=self.timeout,
                )
            except Exception as err:
                raise RequestError('Unable to communicate with Mollie: {error}'.format(error=err))
        return response

    def setup_oauth(self, client_id, client_secret, redirect_uri, scope, set_token=None):
        # TODO: keyword arguments

        """
        :param client_id: (string)
        :param client_secret: (string)
        :param redirect_uri: (string)
        :param scope: Mollie connect permissions (list)
        :param set_token:
        :param get_token:
        :return: authorization url (url)
        """

        # Web Application Flow
        # The steps below outline how to use the default Authorization Grant Type flow
        # to obtain an access token and fetch a protected resource.
        # Here provider is Mollie and the protected resource is the user’s profile.

        # User authorization through redirection.
        # First we will create an authorization url from the base URL given by the provider
        # and the credentials previously obtained.
        # In addition most providers will request that you ask for access to a certain scope.
        from requests_oauthlib import OAuth2Session

        self.client_secret = client_secret
        self.oauth = OAuth2Session(
            client_id,
            redirect_uri=redirect_uri,
            scope=scope,
        )
        authorization_url, state = self.oauth.authorization_url('https://www.mollie.com/oauth2/authorize')

        return authorization_url  # The merchant should visit this url to authorize access.

    def setup_oauth_authorization_response(self, authorization_response):
        """
        :param authorization_response: The full callback URL (string)
        :return: None
        """
        # Fetch an access token from the provider using the authorization code obtained during user authorization.
        self.access_token = self.oauth.fetch_token(
            'https://api.mollie.com/oauth2/tokens',
            authorization_response=authorization_response,
            client_secret=self.client_secret,
        )

    def oauth_refresh_token(self):
        token = {
            'access_token': 'eswfld123kjhn1v5423',
            'refresh_token': 'asdfkljh23490sdf',
            'token_type': 'Bearer',
            'expires_in': '-30',     # initially 3600, need to be updated by you
        }
        client_id = r'foo'
        refresh_url = 'https://provider.com/token'
        protected_url = 'https://provider.com/secret'

        # If needed.
        extra = {
            'client_id': client_id,
            'client_secret': r'potato',
        }

        from requests_oauthlib import OAuth2Session
        client = OAuth2Session(
            client_id,
            token=self.get_token,
            auto_refresh_url=refresh_url,
            auto_refresh_kwargs=extra,
            token_updater=self.set_token
        )
        response = client.get(protected_url)


def generate_querystring(params):
    """
    Generate a querystring suitable for use in the v2 api.

    The Requests library doesn't know how to generate querystrings that encode dictionaries using square brackets:
    https://api.mollie.com/v2/methods?amount[value]=100.00&amount[currency]=USD

    Note: we use `sorted()` to work around a difference in iteration behaviour between Python 2 and 3.
    This makes the output predictable, and ordering of querystring parameters shouldn't matter.
    """
    if not params:
        return None
    parts = []
    for param, value in sorted(params.items()):
        if not isinstance(value, dict):
            parts.append(urlencode({param: value}))
        else:
            # encode dictionary with square brackets
            for key, sub_value in sorted(value.items()):
                composed = '{param}[{key}]'.format(param=param, key=key)
                parts.append(urlencode({composed: sub_value}))
    if parts:
        return '&'.join(parts)
