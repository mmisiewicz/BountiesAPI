import json
import requests
from decimal import Decimal

from web3 import Web3, HTTPProvider
from web3.contract import ConciseContract
from web3.middleware import geth_poa_middleware
from std_bounties.constants import rev_mapped_difficulties, BEGINNER
from std_bounties.contract import data
from std_bounties.models import Token
from utils.functional_tools import pluck

from django.conf import settings
import ipfsapi
import logging


logger = logging.getLogger('django')

web3 = Web3(HTTPProvider(settings.ETH_NETWORK_URL))
if settings.ETH_NETWORK in ['rinkeby', 'consensysrinkeby', 'rinkebystaging']:
    web3.middleware_stack.inject(geth_poa_middleware, layer=0)
bounties_json = json.loads(data)
ipfs = ipfsapi.connect(host='https://ipfs.infura.io')
bounty_data_keys = [
    'uid',
    'description',
    'title',
    'sourceFileName',
    'sourceFileHash',
    'sourceDirectoryHash',
    'webReferenceURL']
fulfillment_data_keys = [
    'description',
    'url',
    'sourceFileName',
    'sourceFileHash',
    'sourceDirectoryHash']


def map_bounty_data(data_hash, bounty_id):
    ipfs_hash = data_hash
    if len(ipfs_hash) != 46 or not ipfs_hash.startswith('Qm'):
        logger.error('Data Hash Incorrect for bounty: {:d}'.format(bounty_id))
        data_JSON = '{}'
    else:
        data_JSON = ipfs.cat(ipfs_hash)

    if len(ipfs_hash) == 0:
        ipfs_hash = 'invalid'

    data = json.loads(data_JSON)
    meta = data.get('meta', {})

    if 'payload' in data:
        data = data.get('payload')

    metadata = data.get('metadata', {})

    experienceLevel = metadata.get('experienceLevel') or data.get('difficulty') or ''
    experienceLevel = 'Advanced' if experienceLevel == 'Expert' else experienceLevel

    formattedExperienceLevel = str(experienceLevel).lower().strip().capitalize()

    metadata.update({'experienceLevel': rev_mapped_difficulties.get(
        formattedExperienceLevel, BEGINNER)})

    data_issuer = data.get('issuer', {})
    if isinstance(data_issuer, str):
        logger.error('Issuer schema incorrect for: {:d}'.format(bounty_id))
        data_issuer = {}

    categories = data.get('categories', [])
    plucked_data = pluck(data, bounty_data_keys)

    bounty = {
        **plucked_data,
        **meta,
        **metadata,
        'private_fulfillments': data.get('privateFulfillments', True),
        'issuer_name': data_issuer.get(
            'name',
            ''),
        'issuer_email': data_issuer.get(
            'email',
            '') or data.get(
                'contact',
                ''),
        'issuer_githubUsername': data_issuer.get(
            'githubUsername',
            ''),
        'issuer_address': data_issuer.get(
            'address',
            ''),
        'revisions': data.get('revisions', None),
        'data_issuer': data_issuer,
        'data': ipfs_hash,
        'data_json': str(data_JSON),
        'data_categories': categories,
    }

    # if 'platform' is gitcoin, also return deadline
    if metadata.get('platform', '') is 'gitcoin':
        bounty.update({'deadline': data.get('expire_date', '')})

    return bounty


def map_fulfillment_data(data_hash, bounty_id, fulfillment_id):
    ipfs_hash = data_hash
    if len(ipfs_hash) != 46 or not ipfs_hash.startswith('Qm'):
        logger.error(
            'Data Hash Incorrect for fulfillment on bounty: {:d} fulfillment: {:d}'.format(
                bounty_id, fulfillment_id))
        data_JSON = '{}'
    else:
        data_JSON = ipfs.cat(ipfs_hash)

    if len(ipfs_hash) == 0:
        ipfs_hash = 'invalid'

    data = json.loads(data_JSON)
    metadata = data.pop('meta', {})
    if 'payload' in data:
        data = data.get('payload')
    data_fulfiller = data.get('fulfiller', {})
    plucked_data = pluck(data, fulfillment_data_keys)

    return {
        'data_json': str(data_JSON),
        'data': ipfs_hash,
        'data_fulfiller': data_fulfiller,
        'fulfiller_name': data_fulfiller.get(
            'name',
            ''),
        'fulfiller_email': data_fulfiller.get(
            'email',
            '') or data.get(
                'contact',
                ''),
        'fulfiller_githubUsername': data_fulfiller.get(
            'githubUsername',
            ''),
        'fulfiller_address': data_fulfiller.get(
            'address',
            ''),
        **plucked_data,
        **metadata,
    }


def calculate_token_quantity(value, decimals):
    return Decimal(value) / Decimal(pow(10, decimals))


def calculate_usd_price(value, decimals, usd_rate):
    return ((Decimal(value) / Decimal(pow(10, decimals))) * Decimal(usd_rate)).quantize(Decimal(10) ** -8)


def get_token_pricing(token_symbol, token_decimals, value):
    try:
        token_model = Token.objects.get(symbol=token_symbol)
        usd_price = calculate_usd_price(
            value, token_decimals, token_model.price_usd)
    except Token.DoesNotExist:
        token_model = None
        usd_price = 0

    return usd_price, token_model


def get_historic_pricing(token_symbol, token_decimals, value, timestamp):
    r = requests.get(
        'https://min-api.cryptocompare.com/data/pricehistorical?fsym={}&tsyms=USD&ts={}&extraParams=bountiesnetwork'.format(
            token_symbol,
            timestamp))
    r.raise_for_status()
    coin_data = r.json()
    if coin_data.get('Response', None) == 'Error':
        usd_price, token_model = get_token_pricing(
            token_symbol, token_decimals, value)
        token_price = token_model.price_usd if token_model else 0
        return usd_price, token_price
    token_price = coin_data[token_symbol]['USD']
    return calculate_usd_price(
        value,
        token_decimals,
        token_price), token_price


def map_token_data(pays_tokens, token_contract, amount):
    token_symbol = 'ETH'
    token_decimals = 18

    if pays_tokens:
        HumanStandardToken_abi = bounties_json['interfaces']['HumanStandardToken']
        DSToken_abi = bounties_json['interfaces']['DSToken']

        try:
            HumanStandardToken = web3.eth.contract(
                abi=HumanStandardToken_abi,
                address=web3.toChecksumAddress(token_contract),
                ContractFactoryClass=ConciseContract
            )
            token_symbol = HumanStandardToken.symbol()
            token_decimals = HumanStandardToken.decimals()
        except OverflowError:
            DSToken = web3.eth.contract(
                abi=DSToken_abi,
                address=web3.toChecksumAddress(token_contract),
                ContractFactoryClass=ConciseContract
            )
            # Symbol in DSToken contract is bytes32 and unused chars are padded
            # with '\x00'
            token_symbol = DSToken.symbol().decode().rstrip('\x00')
            token_decimals = DSToken.decimals()

    usd_price, token_model = get_token_pricing(
        token_symbol, token_decimals, amount)

    return {
        'tokenSymbol': token_symbol,
        'tokenDecimals': token_decimals,
        'token': token_model.id if token_model else None,
        'usd_price': usd_price,
    }
