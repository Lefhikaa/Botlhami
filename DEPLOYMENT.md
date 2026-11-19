# Deploying Botlhami to Azure

Botlhami runs on Azure App Service (Linux, Python 3.12) with Azure Database for PostgreSQL. Email goes through Azure Communication Services. All resources sit in **South Africa North** (Johannesburg), the closest Azure region to Botswana.

After the one-time setup below, every push to `main` is tested and deployed automatically by `.github/workflows/deploy.yml`.

> **Names used below.** The web app is called `botlhami-saxum`, so it will live at `https://botlhami-saxum.azurewebsites.net`. The database server is called `botlhami-db`. If a name is taken, choose another and use it everywhere it appears.

> **Region note.** Azure for Students subscriptions can be limited to certain regions. If South Africa North is refused, Azure lists the regions you're allowed. Pick the closest one, and note it for the technical document, since judges must be told where the data is hosted.

---

## 1. Resource group (1 minute)

Go to **portal.azure.com → Resource groups → Create**.

- Name: `botlhami-rg`
- Region: South Africa North

## 2. PostgreSQL database (about 10 minutes, mostly waiting)

Go to **Create a resource → Azure Database for PostgreSQL → Flexible server → Create**.

| Setting | Value |
| --- | --- |
| Resource group | `botlhami-rg` |
| Server name | `botlhami-db` |
| Region | South Africa North |
| PostgreSQL version | 16 |
| Workload type | Development |
| Compute + storage | Burstable, **B1ms**, 32 GB |
| Authentication | PostgreSQL authentication only |
| Admin username | `botlhamiadmin` |
| Password | A strong password with **letters, numbers and `-` or `_` only**. Avoid `@ : / ? #`, because they break the connection URL |

On the **Networking** tab, choose **Public access** and tick **Allow public access from any Azure service within Azure to this server**.

When the server is ready, open it and go to **Databases → Add**. Name the database `botlhami`.

## 3. Web app (about 5 minutes)

Go to **Create a resource → Web App → Create**.

| Setting | Value |
| --- | --- |
| Resource group | `botlhami-rg` |
| Name | `botlhami-saxum` |
| Publish | Code |
| Runtime stack | Python 3.12 |
| Operating system | Linux |
| Region | South Africa North |
| Pricing plan | **Basic B1**. The free plan sleeps when idle, which breaks the 24/7 requirement |

## 4. Web app settings

Open the web app and go to **Settings → Environment variables → App settings**. Add each setting below, then click **Apply**.

| Name | Value |
| --- | --- |
| `DEBUG` | `False` |
| `SECRET_KEY` | A long random string. Generate one in **Cloud Shell** (the `>_` icon at the top of the portal) with `python3 -c "import secrets; print(secrets.token_urlsafe(50))"` |
| `ALLOWED_HOSTS` | `botlhami-saxum.azurewebsites.net` |
| `CSRF_TRUSTED_ORIGINS` | `https://botlhami-saxum.azurewebsites.net` |
| `SITE_URL` | `https://botlhami-saxum.azurewebsites.net` |
| `DATABASE_URL` | `postgres://botlhamiadmin:YOUR_PASSWORD@botlhami-db.postgres.database.azure.com:5432/botlhami?sslmode=require` |
| `MEDIA_ROOT` | `/home/data/media` |
| `SCM_DO_BUILD_DURING_DEPLOYMENT` | `true` |

Then go to **Settings → Configuration → General settings**:

- **Startup command:** `sh startup.sh`
- **Always on:** On
- **HTTPS only:** On
- **SCM Basic Auth Publishing Credentials:** On. GitHub needs this to deploy.

Click **Save**. Finally, go to **Monitoring → Health check**, turn it on and set the path to `/health/`.

## 5. Connect GitHub (about 3 minutes)

1. On the web app's **Overview**, click **Download publish profile**.
2. In GitHub, go to **Lefhikaa/Botlhami → Settings → Secrets and variables → Actions**.
   - On the **Secrets** tab, click **New repository secret**. Name it `AZURE_WEBAPP_PUBLISH_PROFILE` and paste the whole contents of the downloaded file.
   - On the **Variables** tab, click **New repository variable**. Name it `AZURE_WEBAPP_NAME` with the value `botlhami-saxum`.
3. Go to **Actions → Test and deploy to Azure → Run workflow**. Tests run first, then the app deploys. This takes about 5 minutes.

## 6. First-time data

In the web app, go to **Development Tools → SSH → Go**. Then run:

```bash
python manage.py createsuperuser
python manage.py seed_demo --password "CHOOSE-A-DEMO-PASSWORD"
```

The first command creates your own administrator account. The second creates demo accounts for every role, which the judges can use.

## 7. Email (about 10 minutes)

Until this step is done, verification codes and alerts are written to **Log stream** instead of being emailed.

1. **Create a resource → Email Communication Services.** Put it in `botlhami-rg`, and choose **Africa** as the data location if it's offered. Open it and go to **Provision domains → Add domain → Azure managed domain**. This is free.
2. **Create a resource → Communication Services**, in the same resource group and data location. Open it and go to **Email → Domains → Connect domain**, then select the managed domain.
3. Copy the **connection string** from **Settings → Keys**, and the **MailFrom** address, which looks like `DoNotReply@xxxxxxxx.azurecomm.net`.
4. Add these web app settings:

| Name | Value |
| --- | --- |
| `EMAIL_BACKEND` | `core.email_backends.AzureCommunicationEmailBackend` |
| `ACS_CONNECTION_STRING` | The connection string |
| `ACS_SENDER_ADDRESS` | The MailFrom address |
| `DEFAULT_FROM_EMAIL` | The MailFrom address |

## 8. Availability monitoring (5 minutes, recommended)

On the web app, go to **Monitoring → Application Insights → Turn on**. Then, in Application Insights, go to **Availability → Add standard test**. Use the URL `https://botlhami-saxum-dcbngscjene6gqef.southafricanorth-01.azurewebsites.net/health/ (your app's own address from Overview → Default domain)` with a frequency of 5 minutes. This gives evidence for the 24/7 criterion.

---

## Troubleshooting

- **"Application error" page:** check **Log stream** on the web app. The most common causes are a wrong `DATABASE_URL` or a missing `SECRET_KEY`.
- **"Bad Request (400)":** `ALLOWED_HOSTS` doesn't match the address you opened.
- **CSRF error when signing in:** `CSRF_TRUSTED_ORIGINS` is missing or doesn't start with `https://`.
