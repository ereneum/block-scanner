import os
import aiohttp
import discord
import ens
import io
import base64
import matplotlib.pyplot as plt
from web3 import Web3, HTTPProvider
from discord.ext import commands
from etherscan import Etherscan
from decimal import Decimal

bot = commands.Bot(command_prefix='!scan ')
bot.remove_command('help')
NETWORK = "mainnet"  # or ropsten, kovan, rinkeby etc.
EtherscanApiKey = os.environ['ETHERSCAN_API_KEY']
InfuraApiKey = os.environ['INFURA_API_KEY']

w3 = Web3(HTTPProvider(f"https://mainnet.infura.io/v3/{InfuraApiKey}"))

api = Etherscan(api_key=EtherscanApiKey)


def from_wei(wei):
    return float(wei) / 10**18


def resolve_address(ens_name):
    return w3.ens.address(ens_name)


def get_block_reward(blocknumber):
    block_reward = api.get_block_reward_by_block_number(blocknumber)
    block_reward_eth = from_wei(block_reward['blockReward'])
    return block_reward_eth


async def get_token_balances(address):
    async with aiohttp.ClientSession() as session:
        async with session.get(
                f"https://api.ethplorer.io/getAddressInfo/{address}?apiKey=freekey"
        ) as response:
            if response.status != 200:
                return "Error: Couldn't access the Ethplorer API."
            data = await response.json()

    if not data.get("tokens"):
        return "No tokens found at this address."

    balances = {}
    for token in data["tokens"]:
        if token["tokenInfo"].get("decimals") and int(
                token["tokenInfo"]["decimals"]) != 0:
            balances[token["tokenInfo"]["symbol"]] = {
                "balance":
                float(token["balance"]) /
                10**int(token["tokenInfo"]["decimals"]),
                "contract_address":
                token["tokenInfo"]["address"]
            }
        else:
            balances[
                f"{token['tokenInfo']['name']} (NFT)"] = f"{token['balance']} {token['tokenInfo']['symbol']}"

    return balances


async def get_token_price(contract_address):
    async with aiohttp.ClientSession() as session:
        async with session.get(
                f"https://api.coingecko.com/api/v3/coins/ethereum/contract/{contract_address}"
        ) as response:
            if response.status != 200:
                return None
            data = await response.json()

    if not data.get("market_data"):
        return None

    return float(Decimal(data["market_data"]["current_price"]["usd"]))


last_price = api.get_eth_last_price()
eth_usd_price = float(last_price['ethusd'])
eth_supply = from_wei(api.get_total_eth_supply())


@bot.event
async def on_ready():
    print(f"Bot logged in as {bot.user.name}")


@bot.command()
async def hello(ctx):
    await ctx.send("Hi")


@bot.command()
async def help(ctx):
    embed = discord.Embed(
        title="What is Block Scanner?",
        description=
        "Block Scanner is a Discord bot that provides blockchain information to users in real-time (currently only supports Ethereum Mainnet).",
        color=0xa7bf64,
    )
    embed.set_author(
        name="Block Scanner",
        icon_url="https://i.imgur.com/miJET1v.png",
    )
    embed.add_field(
        name="!scan hello",
        value="Sends a greeting message",
        inline=False,
    )
    embed.add_field(
        name="!scan balance [address or ens name]",
        value=
        "Returns the Ethereum balance of the specified Ethereum address or ENS name",
        inline=False,
    )
    embed.add_field(
        name="!scan gas",
        value="Returns the current gas price",
        inline=False,
    )
    embed.add_field(
        name=
        "!scan balancemulti [address or ens name] [address or ens name]...",
        value=
        "Returns the Ethereum balances of multiple Ethereum addresses or ENS names",
        inline=False,
    )
    embed.add_field(
        name="!scan eth",
        value="Returns the current ETH price in USD",
        inline=False,
    )
    embed.add_field(
        name="!scan ethsupply",
        value="Returns the current total ETH supply",
        inline=False,
    )
    embed.add_field(
        name="!scan blockreward [blocknumber]",
        value="Returns the block reward for the specified block number",
        inline=False,
    )
    embed.add_field(
        name="!scan blocksmined [address or ens name]",
        value=
        "Returns the last 20 blocks mined by the specified Ethereum address or ENS name",
        inline=False,
    )
    embed.add_field(
        name="!scan ens [ens name]",
        value="Resolves the Ethereum address for the specified ENS name",
        inline=False,
    )
    embed.add_field(
        name="!scan portfolio [address or ens name]",
        value=
        "Returns the token balances of the specified Ethereum address. It may take longer to respond on accounts with a large number of tokens.",
        inline=False,
    )
    embed.add_field(
        name="!scan portfoliopic [address or ens name]",
        value=
        "Returns a pie chart of the specified Ethereum address's portfolio. It may take longer to respond on accounts with a large number of tokens.",
        inline=False,
    )
    embed.set_footer(
        text=
        "Please write the ENS name with the '.eth' extension. e.g. vitalik.eth"
    )
    await ctx.send(embed=embed)


@bot.command()
async def balance(ctx, address_or_ens):
    if ".eth" in address_or_ens:
        # Convert the ENS name to an Ethereum address
        address = resolve_address(address_or_ens)
        if address is None:
            await ctx.send("There is no such ENS name.")
    else:
        # If ENS resolution fails, assume that the input is already an Ethereum address
        address = address_or_ens
    short_address = address[:6] + "..." + address[-4:]
    balance = api.get_eth_balance(address)
    balance_in_ether = float(from_wei(balance))
    balance_in_usd = balance_in_ether * eth_usd_price
    await ctx.send(
        f"Balance for {short_address}: {balance_in_ether:.4f} ETH ({balance_in_usd:.2f}$)"
    )


@bot.command()
async def gas(ctx):
    gas_price = api.get_proxy_gas_price()
    gas_price_wei = int(gas_price, 16)
    gas_price_gwei = int(gas_price_wei) // 10**9
    await ctx.send(f"Current gas price : {gas_price_gwei} gwei")


@bot.command()
async def balancemulti(ctx, *addresses):
    responses = []
    for address_or_ens in addresses:
        if ".eth" in address_or_ens:
            # Convert the ENS name to an Ethereum address
            address = resolve_address(address_or_ens)
            if address is None:
                responses.append(
                    f"{address_or_ens} : There is no such ENS name.")
                continue
        else:
            # If ENS resolution fails, assume that the input is already an Ethereum address
            address = address_or_ens

        balance = api.get_eth_balance(address)
        balance_in_ether = from_wei(balance)
        short_address = address[:6] + "..." + address[-4:]
        response = f"{short_address} : {balance_in_ether} ETH"
        responses.append(response)
    await ctx.send('\n'.join(responses))


@bot.command()
async def eth(ctx):
    await ctx.send(f"Current ETH Price : {eth_usd_price}$")


@bot.command()
async def ethsupply(ctx):
    formatted_supply = "{:,.4f}".format(eth_supply)
    await ctx.send(f"Current ETH Supply : {formatted_supply} ETH")


@bot.command()
async def blockreward(ctx, blocknumber):
    reward = get_block_reward(blocknumber)
    await ctx.send(f" Block Reward : {reward} ETH")


@bot.command()
async def blocksmined(ctx, address_or_ens):
    if ".eth" in address_or_ens:
        # Convert the ENS name to an Ethereum address
        address = resolve_address(address_or_ens)
        if address is None:
            await ctx.send("There is no such ENS name.")
    else:
        # If ENS resolution fails, assume that the input is already an Ethereum address
        address = address_or_ens

    try:
        page = 1
        page_size = 20
        blocks_mined = api.get_mined_blocks_by_address_paginated(
            address, page, page_size)
        short_address = address[:6] + "..." + address[-4:]
        blocks_mined_last_20 = blocks_mined[:20]
        response = f"Last 20 blocks mined by {short_address}:\n"
        for i, block in enumerate(blocks_mined_last_20):
            response += f"{i+1}. Block: {block['blockNumber']} - Reward: {get_block_reward(block['blockNumber'])} ETH\n"

        await ctx.send(response)

    except:
        await ctx.send(f"{address_or_ens} has not mined any blocks yet.")


@bot.command()
async def ens(ctx, address_or_ens):
    address = resolve_address(address_or_ens)
    await ctx.send(address)


@bot.command()
async def portfolio(ctx, address_or_ens):
    try:
        if ".eth" in address_or_ens:
            # Convert the ENS name to an Ethereum address
            address = resolve_address(address_or_ens)
            if address is None:
                await ctx.send("There is no such ENS name.")
        else:
            # If ENS resolution fails, assume that the input is already an Ethereum address
            address = address_or_ens
        balances = await get_token_balances(address)
        short_address = address[:6] + "..." + address[-4:]
        response = f"Token balances for {short_address} : \n"
        token_balances = {}
        nft_balances = {}
        for symbol, balance in balances.items():
            if "(NFT)" in symbol:
                nft_balances[symbol] = balance
            else:
                token_balances[symbol] = balance

        if token_balances:
            response += "\nERC20 Token Balances:\n"
            for symbol, balance in token_balances.items():
                contract_address = balance["contract_address"]
                price = await get_token_price(contract_address)
                if price is None:
                    usdbalance = ""
                else:
                    usdbalance = price * float(balance['balance'])
                    usdbalance = f"({usdbalance:.2f})$"
                response += f"{symbol}: {balance['balance']} {usdbalance}\n"

        if nft_balances:
            response += "\nNon-ERC20 Balances (Possibly NFTs):\n"
            for symbol, balance in nft_balances.items():
                short_symbol = symbol[:-6]
                response += f"{short_symbol}: {balance}\n"

        if len(response) > 2000:
            error_message = f"Portfolio exceeds Discord's message limit. To see all balances : https://etherscan.io/address/{address}"
            await ctx.send(error_message)
        else:
            await ctx.send(response)

    except Exception as e:
        await ctx.send(f"Error: {e}")


@bot.command()
async def portfoliopic(ctx, address_or_ens):
    try:
        if ".eth" in address_or_ens:
            # Convert the ENS name to an Ethereum address
            address = resolve_address(address_or_ens)
            if address is None:
                await ctx.send("There is no such ENS name.")
        else:
            # If ENS resolution fails, assume that the input is already an Ethereum address
            address = address_or_ens
        balances = await get_token_balances(address)
        short_address = address[:6] + "..." + address[-4:]
        token_balances = {}
        for symbol, balance in balances.items():
            if "(NFT)" not in symbol:
                contract_address = balance["contract_address"]
                price = await get_token_price(contract_address)
                usd_balance = price * float(
                    balance["balance"]) if price is not None else None
                if usd_balance is not None:
                    token_balances[symbol] = usd_balance

        if not token_balances:
            await ctx.send(
                "No ERC20 token balances found for the given address.")
            return

        # Sort the token balances by USD value in descending order
        sorted_balances = sorted(token_balances.items(),
                                 key=lambda x: x[1],
                                 reverse=True)

        # Calculate the ETH balance and add it to token_balances dictionary
        eth_balance = float(from_wei(api.get_eth_balance(address)))
        usd_eth_balance = eth_usd_price * eth_balance if eth_usd_price is not None else None
        if usd_eth_balance is not None:
            token_balances['ETH'] = usd_eth_balance

        # Get the top 10 token balances including ETH balance
        sorted_balances = sorted(token_balances.items(),
                                 key=lambda x: x[1],
                                 reverse=True)
        top_balances = dict(sorted_balances[:10])

        # Add ETH balance to labels and sizes
        if 'ETH' in token_balances and 'ETH' not in top_balances:
            eth_balance = token_balances['ETH']
            eth_label = f"ETH (${eth_balance:.2f})"
            # Add ETH balance to top_balances and labels
            top_balances[eth_label] = eth_balance
            labels.append(eth_label)
            sizes.append(eth_balance)

        # Create the pie chart
        labels = [
            f"{symbol} (${usd_balance:.2f})"
            for symbol, usd_balance in top_balances.items()
        ]
        sizes = list(top_balances.values())

        fig, ax = plt.subplots()
        ax.pie(sizes,
               labels=labels,
               autopct='%1.1f%%',
               startangle=90,
               shadow=False)
        ax.axis('equal')
        ax.legend()

        # Convert the plot to a PNG image
        buffer = io.BytesIO()
        plt.savefig(buffer, format='png')
        buffer.seek(0)
        image_data = buffer.getvalue()

        # Convert the PNG image to a base64-encoded string
        base64_image = base64.b64encode(image_data).decode('utf-8')

        # Send the image as a message
        await ctx.send(f"Top ERC20 token balances for {short_address}:",
                       file=discord.File(io.BytesIO(
                           base64.b64decode(base64_image)),
                                         filename="portfolio.png"))
    except Exception as e:
        await ctx.send(f"Error: {e}")


DiscordToken = os.environ['TOKEN']
bot.run(DiscordToken)
