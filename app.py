import streamlit as st
from scraper_pro import ProductionVehicleScraper

st.set_page_config(page_title="Universal Dealer Scraper", layout="wide")
st.title("🚗 Universal Dealer Inventory Scraper (Production)")
st.caption("✅ STRICT filtering - ONLY valid vehicle data | ✅ VIN decode automatic | ✅ Duplicate removal")

with st.sidebar:
    st.header("Settings")
    url = st.text_input("Inventory URL", "https://www.acuraofoakville.com/used/search.html")
    headless = st.checkbox("Headless (hard sites pe fail ho sakta hai)", value=False)
    block_images = st.checkbox("Block images (faster)", value=True)

    st.subheader("Listing Load")
    max_scrolls = st.slider("Max scrolls", 5, 30, 15)
    scroll_pause = st.slider("Scroll pause (sec)", 1.0, 5.0, 2.5, 0.5)

    st.subheader("Pagination")
    max_pages = st.slider("Max pages", 1, 50, 10)

    st.subheader("Limits")
    limit = st.number_input("Vehicles limit (0 = no limit)", min_value=0, max_value=5000, value=0, step=10)
    max_links = st.number_input("Max links safety cap", min_value=100, max_value=10000, value=2000, step=100)

    st.markdown("---")
    st.info("💡 **Features:**\n- STRICT URL validation\n- Unwanted data filtered\n- Duplicates removed\n- Only valid vehicles")

run_btn = st.button("▶️ Run Scraper", type="primary")

if run_btn:
    st.info("🔄 Starting scraper... Check console for detailed logs")
    scraper = ProductionVehicleScraper(
        inventory_url=url,
        headless=headless,
        block_images=block_images,
        max_scrolls=int(max_scrolls),
        scroll_pause=float(scroll_pause),
        max_pages=int(max_pages),
        max_links=int(max_links),
    )

    try:
        with st.spinner("Scraping inventory... Check console for progress"):
            df = scraper.run(limit=None if int(limit) == 0 else int(limit))

        st.success(f"✅ Scraping Complete!")
        
        # Show summary stats
        st.subheader("📊 Results Summary")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Valid Vehicles", len(df), help="After filtering invalid/duplicate data")
        with col2:
            vin_count = df['vin'].notna().sum() if 'vin' in df.columns else 0
            st.metric("VINs Found", vin_count)
        with col3:
            price_count = df['price'].notna().sum() if 'price' in df.columns else 0
            st.metric("Prices Found", price_count)
        with col4:
            decoded_count = df['vin_make'].notna().sum() if 'vin_make' in df.columns else 0
            st.metric("VINs Decoded", decoded_count)
        
        # Show data quality info
        st.info(f"ℹ️ **Data Quality:** {len(df)} valid vehicles collected. All duplicates and invalid entries removed. Check console logs for filtering details.")
        
        # Show data
        st.subheader("📋 Scraped Data")
        st.dataframe(df, use_container_width=True, height=400)

        # Download button
        csv_bytes = df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
        st.download_button(
            "⬇️ Download CSV", 
            data=csv_bytes, 
            file_name="inventory_clean.csv", 
            mime="text/csv",
            type="primary"
        )
        
        # Show sample of collected URLs
        with st.expander("🔗 Sample Detail URLs (First 10)"):
            if 'source_url' in df.columns:
                sample_urls = df['source_url'].dropna().head(10).tolist()
                for i, url in enumerate(sample_urls, 1):
                    st.text(f"{i}. {url}")
        
        # Show VIN decode sample
        with st.expander("🔐 VIN Decode Sample (First 5)"):
            if 'vin_make' in df.columns:
                sample_df = df[df['vin_make'].notna()][['vin', 'vin_year', 'vin_make', 'vin_model', 'vin_trim']].head(5)
                if not sample_df.empty:
                    st.dataframe(sample_df, use_container_width=True)
                else:
                    st.warning("No VINs decoded yet")
        
    except Exception as e:
        st.error(f"❌ Error: {str(e)}")
        st.exception(e)
    finally:
        scraper.close()
