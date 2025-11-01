import requests
import time
import unicodedata
from bs4 import BeautifulSoup
from urllib.parse import quote_plus

from django.core.management.base import BaseCommand
from organization.models import NestedTerritory


def normalize_text(text):
    """Cleans up text extracted from HTML tables."""
    if not text:
        return ""
    text = ' '.join(text.split())
    return unicodedata.normalize("NFKC", text).strip()

class Command(BaseCommand):
    help = 'Scrapes Wikipedia infobox data for REGION territories marked as NEEDS_WIKI_SCRAPE.'

    def handle(self, *args, **options):
        # Target only regions that have been marked for scraping
        regions_to_scrape = NestedTerritory.objects.filter(
            type=NestedTerritory.TerritoryType.REGION, 
            boundary_status=NestedTerritory.BoundaryStatus.NEEDS_WIKI_SCRAPE
        )

        if not regions_to_scrape.exists():
            self.stdout.write(self.style.SUCCESS('No regions marked for Wikipedia scraping. Nothing to do.'))
            return

        total_regions = regions_to_scrape.count()
        self.stdout.write(f"Found {total_regions} regions to scrape. Starting process...")

        scraped_count = 0
        failed_count = 0

        for i, territory in enumerate(regions_to_scrape):
            self.stdout.write(f"\n({i+1}/{total_regions}) Processing: {territory.name}")

            url_name = territory.name.replace(' ', '_')
            url = f"https://fr.wikipedia.org/wiki/{quote_plus(url_name)}"
            
            try:
                headers = {'User-Agent': 'HobartDataImportBot/1.0 (https://your-project-url.com; your-email@example.com)'}
                response = requests.get(url, headers=headers, timeout=15)
                response.raise_for_status()

                if response.url.endswith("(homonymie)"):
                    self.stdout.write(self.style.WARNING(f"  -> Skipped (is a disambiguation page)."))
                    territory.boundary_status = NestedTerritory.BoundaryStatus.MANUAL_REVIEW_NEEDED
                    territory.save(update_fields=['boundary_status'])
                    failed_count += 1
                    continue

                soup = BeautifulSoup(response.content, 'html.parser')
                infobox = soup.find('table', {'class': 'infobox_v2'})

                if not infobox:
                    self.stdout.write(self.style.WARNING(f"  -> No infobox found on page."))
                    territory.boundary_status = NestedTerritory.BoundaryStatus.MANUAL_REVIEW_NEEDED
                    territory.save(update_fields=['boundary_status'])
                    failed_count += 1
                    continue

                infobox_data = {}
                rows = infobox.find_all('tr')
                for row in rows:
                    header = row.find('th')
                    data = row.find('td')
                    if header and data:
                        key = normalize_text(header.get_text().lower())
                        value = normalize_text(data.get_text())
                        if key and value:
                            infobox_data[key] = value
                
                if infobox_data:
                    territory.scraped_data = infobox_data
                    territory.boundary_status = NestedTerritory.BoundaryStatus.WIKI_SCRAPED
                    territory.save(update_fields=['scraped_data', 'boundary_status'])
                    self.stdout.write(self.style.SUCCESS(f"  -> Successfully scraped and saved infobox data."))
                    scraped_count += 1
                else:
                    self.stdout.write(self.style.WARNING(f"  -> Infobox found, but no data could be extracted."))
                    territory.boundary_status = NestedTerritory.BoundaryStatus.MANUAL_REVIEW_NEEDED
                    territory.save(update_fields=['boundary_status'])
                    failed_count += 1

            except requests.exceptions.RequestException as e:
                self.stdout.write(self.style.ERROR(f"  -> Failed to download page: {e}"))
                territory.boundary_status = NestedTerritory.BoundaryStatus.MANUAL_REVIEW_NEEDED
                territory.save(update_fields=['boundary_status'])
                failed_count += 1
            
            time.sleep(1) # Be a good internet citizen

        self.stdout.write("\n" + self.style.SUCCESS('Scraping Complete!'))
        self.stdout.write(f'- Successfully scraped data for {scraped_count} territories.')
        self.stdout.write(f'- Marked {failed_count} territories for manual review.')
