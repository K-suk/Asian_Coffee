from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import View
from .models import Item, OrderItem, Order, Payment
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.core.exceptions import ObjectDoesNotExist
from django.contrib.auth.mixins import LoginRequiredMixin
from accounts.models import CustomUser
import stripe
from django.conf import settings
from django.core.mail import BadHeaderError, EmailMessage
from django.http import HttpResponse
import textwrap

class IndexView(View):
    def get(self, request, *args, **kwargs):
        item_data = Item.objects.all()
        return render(request, 'app/index.html', {
            'item_data': item_data
        })
        
class ItemDetailView(View):
    def get(self, request, *args, **kwargs):
        item_data = Item.objects.get(slug=self.kwargs['slug'])
        return render(request, 'app/product.html', {
            'item_data': item_data
        })
        
@login_required
def addItem(request, slug):
    item = get_object_or_404(Item, slug=slug)
    order_item, created = OrderItem.objects.get_or_create(
        item=item,
        user=request.user,
        ordered=False
    )
    order = Order.objects.filter(user=request.user, ordered=False)
    
    if order.exists():
        order = order[0]
        if order.items.filter(item__slug=item.slug).exists():
            order_item.quantity += 1
            order_item.save()
        else:
            order.items.add(order_item)
    else:
        order = Order.objects.create(user=request.user, ordered_date=timezone.now())
        order.items.add(order_item)
        
    return redirect('order')

class OrderView(LoginRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        try:
            order = Order.objects.get(user=request.user, ordered=False)
            context = {
                'order': order
            }
            return render(request, 'app/order.html', context)
        except ObjectDoesNotExist:
            return render(request, 'app/order.html')

@login_required
def removeItem(request, slug):
    item = get_object_or_404(Item, slug=slug)
    order = Order.objects.filter(
        user=request.user,
        ordered=False
    )
    if order.exists():
        order = order[0]
        if order.items.filter(item__slug=item.slug).exists():
            order_item = OrderItem.objects.filter(
                item=item,
                user=request.user,
                ordered=False
            )[0]
            order.items.remove(order_item)
            order_item.delete()
            return redirect('order')
    
    return redirect('product', slug=slug)

@login_required
def removeSingleItem(request, slug):
    item = get_object_or_404(Item, slug=slug)
    order = Order.objects.filter(
        user=request.user,
        ordered=False
    )
    if order.exists():
        order = order[0]
        if order.items.filter(item__slug=item.slug).exists():
            order_item = OrderItem.objects.filter(
                item=item,
                user=request.user,
                ordered=False
            )[0]
            if order_item.quantity > 1:
                order_item.quantity -= 1
                order_item.save()
            else:
                order.items.remove(order_item)
                order_item.delete()
            return redirect('order')
    return redirect('product', slug=slug)

class PaymentView(LoginRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        order = Order.objects.get(user=request.user, ordered=False)
        user_data = CustomUser.objects.get(id=request.user.id)
        context = {
            'order': order,
            'user_data': user_data
        }
        return render(request, 'app/payment.html', context)
    
    def post(self, request, *args, **kwargs):
        stripe.api_key = settings.STRIPE_SECRET_KEY
        order = Order.objects.get(user=request.user, ordered=False)
        user_data = CustomUser.objects.get(id=request.user.id)
        token = request.POST.get('stripeToken')
        order_items = order.items.all()
        amount = order.get_total()
        item_list = []
        for order_item in order_items:
            item_list.append(str(order_item.item) + ":" + str(order_item.quantity))
        description = ''.join(item_list)
        
        charge = stripe.Charge.create(
            amount=amount,
            currency='CAD',
            description=description,
            source=token
        )
        
        payment = Payment(user=request.user)
        payment.stripe_charge_id = charge['id']
        payment.amount = amount
        payment.save()
        
        order_items.update(ordered=True)
        for item in order_items:
            item.save()
            
        order.ordered = True
        order.payment = payment
        order.save()
        subject = 'We got an order'
        contact = textwrap.dedent('''
            {first_name} {last_name} order coffee, and this is detail!
            -------------------
            ■ Name
            {first_name} {last_name}
            
            ■ Email
            {email}
            
            ■ Phone Number
            {tel}
            
            ■ Room Number
            {room_number}
            
            ■ Order
            {description}
            -------------------
            ''').format(
                first_name=user_data.first_name,
                last_name=user_data.last_name,
                email=user_data.email,
                tel=user_data.tel,
                room_number=user_data.room_number,
                description=description
                )
        to_list = [settings.EMAIL_HOST_USER]
        try:
            message = EmailMessage(subject=subject, body=contact, to=to_list)
            message.send()
        except BadHeaderError:
            return HttpResponse('Invalid head is found!')
        return redirect('thanks')
    
class ThanksView(LoginRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        return render(request, 'app/thanks.html')