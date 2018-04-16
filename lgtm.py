from base64 import b64decode
import boto3
from datetime import datetime, timedelta
import re
import os
import random

from slacker import Slacker

pr_match = re.compile(r'<https:\/\/github\.com\/DataDog\/.+\/pull\/\d+>')
ENCRYPTED = os.environ['SLACK_TOKEN']
DECRYPTED = boto3.client('kms').decrypt(CiphertextBlob=b64decode(ENCRYPTED))['Plaintext']

slack = Slacker(DECRYPTED)


def gentle_ping(event, context):
    # Get all the channels
    chan_response = slack.channels.list()
    group_response = slack.groups.list()
    channels = chan_response.body.get('channels', [])
    groups = group_response.body.get('groups', [])

    # Filter just for those channels the bot is a member of
    channels_with_lgtm_bot = filter_channels(channels)
    groups_with_lgtm_bot = filter_channels(groups)

    oldest = (datetime.today() - timedelta(days=1)).strftime('%s')
    for channel in channels_with_lgtm_bot:
        chan_id = channel['id']
        response = slack.channels.history(chan_id, oldest=oldest)
        # Todo - deal with channels that have more than 100 messages
        messages = response.body.get('messages', [])
        # Get all the messages with PR links that don't have reactions
        claimed_num, unclaimed = parse_messages(messages)
        send_message(chan_id, claimed_num, unclaimed)

    for channel in groups_with_lgtm_bot:
        chan_id = channel['id']
        response = slack.groups.history(chan_id, oldest=oldest)
        # Todo - deal with channels that have more than 100 messages
        messages = response.body.get('messages', [])
        # Get all the messages with PR links that don't have reactions
        claimed_num, unclaimed = parse_messages(messages)
        send_message(chan_id, claimed_num, unclaimed)

def filter_channels(channels):
    channels_with_lgtm_bot = []
    for channel in channels:
        if channel.get('is_member'):
            channels_with_lgtm_bot.append(channel)
    return channels_with_lgtm_bot

def parse_messages(messages):
    claimed = set()
    unclaimed = set()
    for message in messages:
        if message.get('type') != 'message':
            continue
        text = message.get('text')
        match = re.search(pr_match, text)
        if match:
            if message.get('reactions'):
                claimed.add(match.group(0))
            else:
                unclaimed.add(match.group(0))
        # Sometimes messages get posted twice, and one of them is reacted to.
        # We'll assume if we see the same PR, and one is claimed, that it's been claimed
        unclaimed.difference_update(claimed)
    return len(claimed), unclaimed


def send_message(chan_id, claimed_num, unclaimed_prs):
    total_prs = claimed_num + len(unclaimed_prs)
    if total_prs == 0:
        slack.chat.post_message(chan_id, 'No PRs today, huh? Must be a holiday in France :france:', as_user=True)
        return
    message = '''Today\'s :pr: stats :chart_with_upwards_trend::
- PRs posted in the channel today: {0} {1}
- PRs reviewed today: {2} {3}'''.format(total_prs, get_emoji(total_prs), claimed_num, get_emoji(claimed_num))
    if len(unclaimed_prs) != 0:
        message = message + '\nThere are still {0} unreviewed PRs today - please review one if you can! :eyes:'.format(len(unclaimed_prs))
    slack.chat.post_message(chan_id, message, as_user=True)
    for pr in unclaimed_prs:
        slack.chat.post_message(chan_id, '- {0}'.format(pr), as_user=True)


def get_emoji(num):
    awesome_emojis = [':metal2:', ':pizzaparrot:', ':success:', ':boom:']
    sad_emojis = [':crickets:', ':sadcheese:', ':sadpup:']
    if num <= 2:
        return random.choice(sad_emojis)
    else:
        return random.choice(awesome_emojis)
