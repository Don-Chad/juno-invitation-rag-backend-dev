<?php
/**
 * Plugin Name: AVA Subscription Sync
 * Description: Syncs WooCommerce subscription status with AVA Backend
 * Version: 1.2.0
 * Author: AVA Team
 */

if (!defined('ABSPATH')) {
    exit;
}

class AVA_Subscription_Manager {
    
    private $token_server_url;
    private $site_id;
    private $api_key;
    
    public function __construct() {
        $this->token_server_url = get_option('ava_token_server_url', 'https://token.makecontact.io');
        $this->site_id = get_option('ava_site_id', 'juno_prod');
        $this->api_key = get_option('ava_api_key');
        
        // 1. Initial Activation (New Purchase)
        add_action('woocommerce_order_status_completed', [$this, 'handle_purchase_complete'], 10, 1);
        
        // 2. Deactivation Hooks (Expiry/Cancellation)
        add_action('woocommerce_subscription_status_expired', [$this, 'handle_subscription_deactivated'], 10, 1);
        add_action('woocommerce_subscription_status_cancelled', [$this, 'handle_subscription_deactivated'], 10, 1);
        
        // 3. Security Hook (Email Change)
        add_action('profile_update', [$this, 'handle_email_change'], 10, 2);
    }
    
    public function handle_purchase_complete($order_id) {
        $order = wc_get_order($order_id);
        if (!$order || !$this->order_contains_ava_product($order)) return;
        
        $user = $order->get_user();
        if (!$user) return;

        $this->notify_ava_backend('user_created', [
            'wpUserId' => $user->ID,
            'email' => $user->user_email,
            'displayName' => $user->display_name,
            'subscriptionStatus' => 'active'
        ]);
    }

    public function handle_subscription_deactivated($subscription) {
        $user = $subscription->get_user();
        if (!$user) return;

        $this->notify_ava_backend('subscription_expired', [
            'wpUserId' => $user->ID,
            'email' => $user->user_email,
            'subscriptionStatus' => $subscription->get_status()
        ]);
    }

    public function handle_email_change($user_id, $old_user_data) {
        $new_user_data = get_userdata($user_id);
        $old_email = strtolower($old_user_data->user_email);
        $new_email = strtolower($new_user_data->user_email);
        
        if ($old_email !== $new_email) {
            $this->notify_ava_backend('email_changed', [
                'wpUserId' => $user_id,
                'oldEmail' => $old_email,
                'newEmail' => $new_email,
                'displayName' => $new_user_data->display_name
            ]);
        }
    }
    
    private function notify_ava_backend($eventType, $data) {
        if (isset($data['email'])) $data['email'] = strtolower($data['email']);
        $payload = [
            'eventType' => $eventType, 
            'siteId' => $this->site_id, 
            'timestamp' => current_time('mysql'), 
            'data' => $data
        ];
        
        wp_remote_post($this->token_server_url . '/api/webhook/subscription', [
            'headers' => [
                'Content-Type' => 'application/json', 
                'X-AVA-API-Key' => $this->api_key, 
                'X-AVA-Site-ID' => $this->site_id
            ],
            'body' => json_encode($payload),
            'timeout' => 15
        ]);
    }
    
    private function order_contains_ava_product($order) {
        $ava_product_ids = get_option('ava_product_ids', []);
        if (is_string($ava_product_ids)) $ava_product_ids = explode(',', $ava_product_ids);
        foreach ($order->get_items() as $item) {
            if (in_array($item->get_product_id(), $ava_product_ids)) return true;
        }
        return false;
    }
}

new AVA_Subscription_Manager();
