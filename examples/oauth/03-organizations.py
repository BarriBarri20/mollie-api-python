# coding=utf-8

from __future__ import print_function

from mollie.api.error import Error


ORGANIZATION_ID = 'org_12345678'


def main(client):
    try:
        body = ''

        # https://docs.mollie.com/reference/v2/organizations-api/current-organization

        body += '<h1>Get current organization</h1>'
        response = client.organizations.get('me')

        print(response)
        body += str(response)

        # https://docs.mollie.com/reference/v2/organizations-api/current-organization

        organisation_id = response.id

        body += '<h1>Get organization</h1>'
        response = client.organizations.get(organisation_id)

        print(response)
        body += str(response)

        return body

    except Error as err:
        return 'API call failed: {error}'.format(error=err)
