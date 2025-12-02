# Dominion Energy Home Assistant Integration

A Home Assistant custom integration for monitoring your Dominion Energy electricity usage with high-resolution 30-minute interval data.

## Features

- 30-minute interval energy usage data
- Daily and monthly usage totals
- Cost estimation with multiple calculation modes:
  - **API Estimate**: Derives rate from your actual bill (charges / usage)
  - **Fixed Rate**: Single $/kWh rate
  - **Time-of-Use**: Peak and off-peak rates by hour
- Full Energy Dashboard compatibility
- Automatic token refresh

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Click the three dots in the top right corner
3. Select "Custom repositories"
4. Add this repository URL and select "Integration" as the category
5. Click "Add"
6. Search for "Dominion Energy" and install it
7. Restart Home Assistant

### Manual Installation

1. Copy the `custom_components/dominion_energy` folder to your Home Assistant `config/custom_components/` directory
2. Restart Home Assistant

## Setup

### Step 1: Get API Tokens

Due to CAPTCHA protection, initial authentication requires extracting tokens from your browser.

#### Option A: Using dompower CLI (Recommended)

1. Install the dompower library:
   ```bash
   pip install dompower
   ```

2. Run the auth helper:
   ```bash
   dompower auth-helper --open-browser
   ```

3. Follow the on-screen instructions to:
   - Log in to your Dominion Energy account
   - Extract tokens from browser DevTools
   - Enter them in the CLI

#### Option B: Manual Token Extraction

1. Go to https://login.dominionenergy.com/CommonLogin?SelectedAppName=Electric
2. Log in with your Dominion Energy credentials
3. Open browser DevTools (F12)
4. Go to the Network tab
5. Look for requests to `prodsvc-dominioncip.smartcmobile.com`
6. Find the `Authorization` header (starts with `Bearer `)
7. Extract the access token (part after "Bearer ")
8. Look in the response or Local Storage for the refresh token

### Step 2: Add Integration

1. Go to Home Assistant Settings > Devices & Services
2. Click "Add Integration"
3. Search for "Dominion Energy"
4. Enter your:
   - Access Token
   - Refresh Token
   - Account Number (from your bill)
   - Meter Number (from your bill)

### Step 3: Configure Cost Calculation (Optional)

1. After setup, click "Configure" on the integration
2. Choose your cost calculation method:
   - **API Estimate**: Uses your actual bill rate (recommended)
   - **Fixed Rate**: Enter a single $/kWh rate
   - **Time-of-Use**: Configure peak/off-peak rates and hours

## Sensors

| Sensor | Description | State Class |
|--------|-------------|-------------|
| Latest Interval Usage | Most recent 30-minute reading (kWh) | measurement |
| Daily Usage | Today's total consumption (kWh) | total_increasing |
| Monthly Usage | Current month's consumption (kWh) | total_increasing |
| Daily Cost | Estimated cost for today ($) | total |
| Monthly Cost | Estimated cost for current month ($) | total |

## Energy Dashboard

The Daily Usage and Monthly Usage sensors are compatible with Home Assistant's Energy Dashboard:

1. Go to Settings > Dashboards > Energy
2. Add the "Daily Usage" sensor as an electricity consumption source

## Token Expiration

Tokens automatically refresh every 30 minutes. If authentication fails:

1. Home Assistant will show a notification to re-authenticate
2. Run `dompower auth-helper` to get fresh tokens
3. Enter the new tokens in the re-authentication flow

## Troubleshooting

### "Cannot connect to API"
- Check your internet connection
- Verify Dominion Energy services are online

### "Invalid tokens"
- Tokens may have expired after extended inactivity
- Run `dompower auth-helper` to get fresh tokens

### Missing data
- Data may take up to 30 minutes to appear after setup
- Historical data availability depends on Dominion Energy's API

## API Constants

The Dominion Energy API uses SAP Customer Data Cloud (Gigya) for authentication. The following API key is the default for all users:

```
GIGYA_API_KEY = "4_6zEg-HY_0eqpgdSONYkJkQ"
```

This is a public client identifier embedded in the Dominion Energy web app. It can be overridden via the `GIGYA_API_KEY` environment variable if Dominion updates it.

## Support

- [Report Issues](https://github.com/YeomansII/ha-dominion-energy/issues)
- [dompower Library](https://github.com/YeomansII/dompower)

## License

MIT License
