import json
import string
from django.http import JsonResponse
from django.utils.crypto import get_random_string
from django.views.decorators.csrf import csrf_exempt
#from ..apps.payment.models import Payment

_allowed = string.ascii_letters + string.digits
def simulate_generate_payment_id():
    return get_random_string(length=25, allowed_chars=_allowed)

@csrf_exempt
def simulate_payment_response(request):
    # POST
    #payment_ref = '67e8729f-5d53-4602-807e-14e6cfbe9c67'
    
    payload = json.loads(request.body)
    payment_ref = payload['reference'] 
    
    
    next_url = f'http://localhost:8004/debit-card/confirmation/?payment_ref={payment_ref}'
    json_data={
        'payment_id': simulate_generate_payment_id(),
        '_links': {
            'next_url': {
                'method': 'GET',
                'href': next_url #govuk_url(self.payment_process_path),
            }
        }
    }
    return JsonResponse(json_data, status=201)

_payment_idx = 0
def simulate_get_payment_response_generate_state(processor_id):
    global _payment_idx
    #payment = Payment.objects.get(processor_id=processor_id)

    success = {
        "status": "success",
        "finished": True
    }
    failed_expired = {
        "status": "failed",
        "finished": True,
        "message": "Payment expired",
        "code": "P0020"
    }
    failed_debit_canceled = {
        "status": "failed",
        "finished": True,
        "message": "Payment cancelled",
        "code": "P0030"
    }
    failed_debit_declined = {
        "status": "failed",
        "finished": True,
        "message": "Payment declined",
        "code": "P0010"
    }
    capturable = {
        "status": "capturable",
        "finished": False
    },

    tetris_array = [success, failed_expired, failed_debit_canceled, failed_debit_declined]
    next_state = tetris_array[_payment_idx]
    _payment_idx += 1
    if _payment_idx > 2:
        _payment_idx = 0

    return failed_debit_canceled

@csrf_exempt
def simulate_get_payment_response(request, processor_id):
    # GET
    print(f'uuid_slug: {processor_id}')

    response_state = simulate_get_payment_response_generate_state(processor_id)

    json_data = {
        "created_date": "2019-07-11T10:36:26.988Z",
        "amount": 3750,
        "state": response_state,
        "description": "Pay your council tax",
        "reference": '67e8729f-5d53-4602-807e-14e6cfbe9c67',
        "language": "en",
        "metadata": {
            "ledger_code": "AB100",
            "internal_reference_number": 200
        },
        "security_check": {
            "status": "accepted",
            "user_actioned": False,
        },
        "email": "sherlock.holmes@example.com",
        "card_details": {
            "card_brand": "Visa",
            "card_type": "debit",
            "last_digits_card_number": "1234",
            "first_digits_card_number": "123456",
            "expiry_date": "04/24",
            "cardholder_name": "Sherlock Holmes",
            "billing_address": {
                "line1": "221 Baker Street",
                "line2": "Flat b",
                "postcode": "NW1 6XE",
                "city": "London",
                "country": "GB"
            }
        },
        "payment_id": "hu20sqlact5260q2nanm0q8u93",
        "authorisation_mode": "web",
        "authorisation_summary": {
            "three_d_secure": {
            "required": True
            }
        },
        "refund_summary": {
            "status": "available",
            "amount_available": 3500,
            "amount_submitted": 500
        },
        "settlement_summary": {
            "capture_submit_time": "2019-07-12T17:15:000Z",
            "captured_date": "2019-07-12",
            "settled_date": "2019-07-12"
        },
        "delayed_capture": False,
        "moto": False,
        "corporate_card_surcharge": 250,
        "total_amount": 4000,
        "fee": 200,
        "net_amount": 3800,
        "payment_provider": "worldpay",
        "provider_id": "10987654321",
        "return_url": "https://your.service.gov.uk/completed",
        "_links": {
            "self": {
                "href": "https://publicapi.payments.service.gov.uk/v1/payments/hu20sqlact5260q2nanm0q8u93",
                "method": "GET"
                },
            "events": {
                "href": "https://publicapi.payments.service.gov.uk/v1/payments/hu20sqlact5260q2nanm0q8u93/events",
                "method": "GET"
                },
            "refunds": {
                "href": "https://publicapi.payments.service.gov.uk/v1/payments/hu20sqlact5260q2nanm0q8u93/refunds",
                "method": "GET"
            }
        }
        }
    return JsonResponse(json_data, status=200)