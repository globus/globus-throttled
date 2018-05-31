import time

import tornado.web


# Token Bucket algorithm params (defaults)
# fill rate is num tokens gained per second
TOKEN_BUCKET_FILL_RATE = 1
# bucket max is maximum number of tokens a requester can accrue
TOKEN_BUCKET_MAX = 10
# bucket start is the number of tokens each bucket starts with
TOKEN_BUCKET_START = TOKEN_BUCKET_MAX


class Throttler(object):
    """
    A generic object which implements the Token Bucket throttling algorithm.
    Uses a simple 2-tier nested dict of storage to partition and sort requests
    by the requester and the resource being requested.

    The only methods you should need (other than the constructor) are

      `Throttler.handle_event`
      Consumes a dictionary representing some input event that may or may not
      be throttled and returns a data dict with info about whether or not to
      throttle the request.

      `Throttler.cleanup`
      Cleans out the token buckets with a two phase mark-and-sweep pass.
    """
    __slots__ = ['_resource_buckets']

    def __init__(self):
        """
        The main attribute of a Throttler is a set of data buckets for
        different throttleable resources.
        """
        self._resource_buckets = {}

    def _get_item(self, resource_id, requester_id, now, params):
        """
        Retrieve a data item about the throttling state of a resource +
        requester combination. Requires that we pass the current time (now) in
        order to ensure that all functionality in the Throttler has a
        consistent view of the time.
        """
        # get the collection of requester buckets for a resource ID
        # if absent, initialize it as an empty dict
        try:
            bucket_collection = self._resource_buckets[resource_id]
        except KeyError:
            bucket_collection = self._resource_buckets[resource_id] = {}

        # now, look for an item that represents this requester in that resource
        # bucket, and if it's absent initialize it as a dict containing the
        # last access time and the number of available tokens
        try:
            item = bucket_collection[requester_id]
        except KeyError:
            item = bucket_collection[requester_id] = {
                'last_access': now,
                'num_tokens': params['bucket_start'],
                'last_params': params}

        return item

    @staticmethod
    def _update_item(item, now, params):
        """
        Add tokens to a bucket based on the amount of time elapsed
        Update last access time
        """
        last_access = item['last_access']
        num_tokens = item['num_tokens']

        # delta is, at worst, 0, in case of bad / inaccurate time comparisons
        delta = max(0, params['fill_rate'] * (now - last_access))

        item['num_tokens'] = min(params['bucket_max'], num_tokens + delta)
        item['last_access'] = now
        item['last_params'] = params

    def _consume_token(self, resource_id, requester_id, now, params):
        """
        Get and update an item, then attempt to consume a token from that item.
        An item is a token bucket for a resource ID + requester ID.

        Returns True if a token was consumed, and False if there was
        insufficient capacity for a token to be consumed (meaning that the
        request should probably be throttled).
        """
        item = self._get_item(resource_id, requester_id, now, params)
        Throttler._update_item(item, now, params)

        new_val = item['num_tokens'] - 1
        if new_val < 0:
            return False
        else:
            item['num_tokens'] = new_val
            return True

    @staticmethod
    def _validate_request(request):
        for x in ('requester_id', 'resource_id'):
            if x not in request:
                raise tornado.web.HTTPError(
                    400, reason='{} is required'.format(x))

        params = request.get('throttle_params', {})
        for x in ('fill_rate', 'bucket_max', 'bucket_start'):
            if not isinstance(params.get(x, 0), int):
                raise tornado.web.HTTPError(
                    400, reason='throttle_params.{} must be an int'.format(x))

    def handle_event(self, event):
        '''
        Events are throttle requests. Format documented in README doc.

        handle_event() consumes an event, finds its token bucket, attempts to
        spend a token from that bucket, and then returns a datadict with two
        keys:

          - allow_request: A boolean. True means don't throttle, False means
            that the throttling limits have been exceeded.
          - denial_details: A string or null. Contains any message from the
            throttler back to the requester.
        '''
        self._validate_request(event)

        requester_id = event['requester_id']
        resource_id = event['resource_id']

        throttle_params = event.get('throttle_params', {})
        evaluated_params = {
            'fill_rate': throttle_params.get(
                'fill_rate', TOKEN_BUCKET_FILL_RATE),
            'bucket_max': throttle_params.get(
                'bucket_max', TOKEN_BUCKET_MAX),
            'bucket_start': throttle_params.get(
                'bucket_start', TOKEN_BUCKET_START),
        }

        now = time.time()

        # add tokens based on time elapsed, update last access time, and
        # attempt to remove a token (if possible)
        has_capacity = self._consume_token(
            requester_id, resource_id, now, evaluated_params)

        if has_capacity:
            print('"{}" "{}" allowed'.format(requester_id, resource_id))
            return {'allow_request': True, 'denial_details': None}
        else:
            print('"{}" "{}" denied'.format(requester_id, resource_id))
            return {'allow_request': False,
                    'denial_details': 'No detail today!'}

    def cleanup(self):
        if len(self._resource_buckets) == 0:
            print('throttler empty; skip cleanup')
            return

        print('starting cleanup pass')

        # MARK
        marked = set()
        total_items = 0
        for resource_id, bucket_collection in self._resource_buckets.items():
            for requester_id, item in bucket_collection.items():
                total_items += 1

                self._update_item(item, time.time(), item['last_params'])
                if item['num_tokens'] >= item['last_params']['bucket_max']:
                    marked.add((resource_id, requester_id))

        # SWEEP
        for (resource_id, requester_id) in marked:
            self._resource_buckets[resource_id].pop(requester_id, None)
            if len(self._resource_buckets[resource_id]) == 0:
                self._resource_buckets.pop(resource_id, None)

        print('cleanup done. total: {} removed: {}'
              .format(total_items, len(marked)))
