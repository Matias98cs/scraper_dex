from django.db import models

class Category(models.Model):
    name = models.CharField(max_length=255, unique=True)
    parent = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='children'
    )

    class Meta:
        db_table = 'category'


class Brand(models.Model):
    name = models.CharField(max_length=255, unique=True)

    class Meta:
        db_table = 'brand'


class Product(models.Model):
    name = models.CharField(max_length=255)
    brand = models.ForeignKey(Brand, on_delete=models.PROTECT)
    category = models.ForeignKey(Category, on_delete=models.PROTECT)
    product_class = models.CharField(max_length=100, db_column='class')
    model_code = models.CharField(max_length=100, null=True, blank=True)
    sku = models.CharField(max_length=100, null=True, blank=True)
    image_url = models.URLField(max_length=500, null=True, blank=True)
    link = models.URLField(max_length=500)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        db_table = 'product'

class ProductVariant(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='variants')
    variant_type = models.CharField(max_length=100)
    value = models.CharField(max_length=255)

    class Meta:
        db_table = 'product_variant'

class Page(models.Model):
    name = models.CharField(max_length=255)

    class Meta:
        db_table = 'page'

class ProductPage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='pages')
    page = models.ForeignKey(Page, on_delete=models.CASCADE, related_name='products')
    cuotas = models.CharField(max_length=255, null=True, blank=True)
    payment_info = models.TextField(null=True, blank=True)
    shipping_info = models.TextField(null=True, blank=True)

    class Meta:
        db_table = 'product_page'

class Pricing(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='pricings')
    page = models.ForeignKey(Page, on_delete=models.CASCADE, related_name='pricings')
    price_current = models.DecimalField(max_digits=12, decimal_places=2)
    price_prev = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    discount = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    free_shipping = models.BooleanField(default=False)
    currency = models.CharField(max_length=10)
    recorded_at = models.DateTimeField()

    class Meta:
        db_table = 'pricing'

class ProductQuota(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='quotas')
    page = models.ForeignKey(Page, on_delete=models.CASCADE, related_name='quotas')
    payment_method = models.CharField(max_length=100)
    quota_count = models.IntegerField()
    price_per_quota = models.DecimalField(max_digits=12, decimal_places=2)
    interest_free = models.BooleanField(default=False)

    class Meta:
        db_table = 'product_quota'

class Size(models.Model):
    name = models.CharField(max_length=100)

    class Meta:
        db_table = 'size'

class ProductSize(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='sizes')
    size = models.ForeignKey(Size, on_delete=models.CASCADE, related_name='products')
    available = models.IntegerField()
    country = models.CharField(max_length=100, null=True, blank=True)

    class Meta:
        db_table = 'product_size'
