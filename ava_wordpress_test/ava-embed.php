<?php
/**
 * Plugin Name: AVA Embed Assistant
 * Description: Securely embeds the AVA Voice Assistant with subscription gating
 * Version: 1.1.0
 * Author: AVA Team
 */

if (!defined('ABSPATH')) {
    exit;
}

class AVA_Embed_Manager {
    
    private $assistant_url;
    private $site_id;
    
    public function __construct() {
        $this->assistant_url = get_option('ava_assistant_url', 'https://the-invitation-2.makecontact.io');
        $this->site_id = get_option('ava_site_id', 'juno_prod');
        
        add_shortcode('ava_assistant', [$this, 'render_ava_embed']);
        add_action('admin_menu', [$this, 'add_admin_menu']);
        add_action('admin_init', [$this, 'register_settings']);
    }

    /**
     * Render the AVA Embed Shortcode
     * [ava_assistant width="100%" height="800px"]
     */
    public function render_ava_embed($atts) {
        $atts = shortcode_atts([
            'width' => '100%',
            'height' => '800px'
        ], $atts);

        // 1. Check if user is logged in
        if (!is_user_logged_in()) {
            return '<div class="ava-notice">Log a.u.b. in om de assistent te gebruiken.</div>';
        }

        // 2. Check for active subscription (Requires WooCommerce Subscriptions)
        if (!$this->user_has_active_subscription()) {
            return '<div class="ava-notice">Een actief abonnement is vereist voor toegang tot de assistent.</div>';
        }

        // 3. Get user email
        $current_user = wp_get_current_user();
        $user_email = urlencode(strtolower($current_user->user_email));

        // 4. Render Iframe
        ob_start();
        ?>
        <div class="ava-container" style="width: <?php echo esc_attr($atts['width']); ?>; height: <?php echo esc_attr($atts['height']); ?>;">
            <iframe 
                src="<?php echo esc_url($this->assistant_url . '/embed?user_email=' . $user_email . '&site_id=' . $this->site_id); ?>"
                width="100%"
                height="100%"
                style="border: none; border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.1);"
                allow="autoplay"
                sandbox="allow-same-origin allow-scripts allow-popups allow-forms allow-popups-to-escape-sandbox">
            </iframe>
        </div>
        <?php
        return ob_get_clean();
    }

    /**
     * Helper to check for active WooCommerce subscription
     */
    private function user_has_active_subscription() {
        if (!function_exists('wcs_user_has_subscription')) {
            return current_user_can('manage_options'); // Allow admins if WCS not installed
        }

        $ava_product_ids = get_option('ava_product_ids', []);
        if (is_string($ava_product_ids)) {
            $ava_product_ids = explode(',', $ava_product_ids);
        }

        return wcs_user_has_subscription(get_current_user_id(), $ava_product_ids, 'active');
    }

    public function add_admin_menu() {
        add_options_page('AVA Settings', 'AVA Embed', 'manage_options', 'ava-embed-settings', [$this, 'render_settings_page']);
    }

    public function register_settings() {
        register_setting('ava_embed_settings', 'ava_assistant_url');
        register_setting('ava_embed_settings', 'ava_token_server_url');
        register_setting('ava_embed_settings', 'ava_site_id');
        register_setting('ava_embed_settings', 'ava_api_key');
        register_setting('ava_embed_settings', 'ava_product_ids');
    }

    public function render_settings_page() {
        ?>
        <div class="wrap">
            <h1>AVA Assistant Settings</h1>
            <form method="post" action="options.php">
                <?php settings_fields('ava_embed_settings'); ?>
                <table class="form-table">
                    <tr>
                        <th scope="row">Assistant URL (Frontend)</th>
                        <td><input type="url" name="ava_assistant_url" value="<?php echo esc_attr(get_option('ava_assistant_url', 'https://the-invitation-2.makecontact.io')); ?>" class="regular-text"></td>
                    </tr>
                    <tr>
                        <th scope="row">Token Server URL (Backend)</th>
                        <td><input type="url" name="ava_token_server_url" value="<?php echo esc_attr(get_option('ava_token_server_url', 'https://token.makecontact.io')); ?>" class="regular-text"></td>
                    </tr>
                    <tr>
                        <th scope="row">Site ID</th>
                        <td><input type="text" name="ava_site_id" value="<?php echo esc_attr(get_option('ava_site_id', 'juno_prod')); ?>" class="regular-text"></td>
                    </tr>
                    <tr>
                        <th scope="row">API Key (Webhook)</th>
                        <td><input type="password" name="ava_api_key" value="<?php echo esc_attr(get_option('ava_api_key')); ?>" class="regular-text"></td>
                    </tr>
                    <tr>
                        <th scope="row">WooCommerce Product IDs</th>
                        <td><input type="text" name="ava_product_ids" value="<?php echo esc_attr(get_option('ava_product_ids')); ?>" class="regular-text">
                        <p class="description">Komma-gescheiden ID's van producten die toegang geven.</p></td>
                    </tr>
                </table>
                <?php submit_button(); ?>
            </form>
        </div>
        <?php
    }
}

new AVA_Embed_Manager();
