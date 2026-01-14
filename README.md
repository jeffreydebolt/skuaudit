# SKUaudit

Amazon FBA margin audit • Benchmarked against real seller data.

## Pricing

- **Free:** Up to 10 SKUs per audit
- **Unlimited:** $29 one-time (coming soon)

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploy to Streamlit Cloud (free)

1. Push to GitHub
2. Go to share.streamlit.io
3. Connect repo, point to app.py
4. Add secrets (optional, for data collection):
   - SUPABASE_URL
   - SUPABASE_KEY
5. Done

## Database setup (optional)

To collect anonymized benchmark data over time:

1. Create a Supabase project at supabase.com
2. Run `schema.sql` in the SQL editor
3. Add your SUPABASE_URL and SUPABASE_KEY to Streamlit secrets

The app works without a database - it just won't save data to improve benchmarks.

## What gets stored (if enabled)

Only anonymized data:
- Price tier (e.g., "$25-50")
- Fulfillment % 
- COGS %
- Margin %
- Timestamp

NO product names, ASINs, SKUs, or business identifiers.

## Next steps

- [ ] Add Stripe for payments
- [ ] Add CSV upload for costs (bulk)
- [ ] Add export to CSV/PDF
- [ ] Dashboard showing benchmark trends over time
- [ ] Category-level benchmarks
