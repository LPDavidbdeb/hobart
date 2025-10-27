from django.db import models

class FAQ(models.Model):
    """Represents a single Frequently Asked Question."""
    question = models.CharField(max_length=255)
    answer = models.TextField()
    display_order = models.PositiveIntegerField(default=0, help_text="FAQs will be displayed in ascending order.")

    class Meta:
        ordering = ['display_order', 'question']
        verbose_name = "FAQ"
        verbose_name_plural = "FAQs"

    def __str__(self):
        return self.question
