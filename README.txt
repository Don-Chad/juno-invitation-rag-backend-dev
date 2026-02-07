# AVA Voice Assistant - WordPress Integration

Deze map bevat de WordPress scripts om de AVA Voice Assistant te integreren met WooCommerce.

## Installatie Instructies

1.  **Bestanden uploaden:**
    Upload `ava-embed.php` en `ava-subscription.php` naar de `/wp-content/plugins/` map van je WordPress installatie (liefst in een eigen map genaamd `ava-voice-assistant`).
2.  **Plugins Activeren:**
    Ga naar het WordPress dashboard en activeer de plugins:
    - **AVA Embed Assistant**
    - **AVA Subscription Sync**
3.  **Configuratie:**
    Ga naar **Instellingen > AVA Embed** en vul de volgende gegevens in:
    - **Assistant URL (Frontend):** `https://the-invitation-2.makecontact.io`
    - **Token Server URL (Backend):** `https://token.makecontact.io`
    - **Site ID:** `juno_prod`
    - **API Key (Webhook):** `a26b34a050413d35bdd715964b37218a51b6d5fe6fe9f7692169b84f93cd8d28`
    - **WooCommerce Product IDs:** Vul hier de ID's in van de producten (gescheiden door komma's) die toegang geven tot de assistent.

4.  **Shortcode Gebruiken:**
    Gebruik de shortcode `[ava_assistant]` op elke pagina waar je de assistent wilt tonen. De plugin controleert automatisch of de gebruiker is ingelogd en een actief abonnement heeft.

## Beveiliging
De API Key zorgt ervoor dat alleen jouw WordPress site wijzigingen kan doorgeven aan de AVA backend. Deel deze sleutel niet met onbevoegden.
