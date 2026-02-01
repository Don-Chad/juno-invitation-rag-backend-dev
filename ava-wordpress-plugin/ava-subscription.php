<?php
/**
 * Plugin Name: AVA Subscription Sync
 * Description: Syncs WooCommerce subscription status with AVA Backend
 * Version: 1.0.0
 * Author: AVA Team
 */

if (!defined('ABSPATH')) {
    exit;
}

class AVA_Subscription_Manager {
    
    private $ava_backend_url;
    private $site_id;
    private $api_key;
    
    public function __construct() {
        $this->ava_backend_url = get_option('ava_backend_url');
        $this->site_id = get_option('ava_site_id');
        $this->api_key = get_option('ava_api_key');
        
        // WooCommerce hooks
        add_action('woocommerce_order_status_completed', [$this, 'handle_purchase_complete'], 10, 1);
        add_action('woocommerce_subscription_status_active', [$this, 'handle_subscription_activated'], 10, 1);
        add_action('woocommerce_subscription_status_expired', [$this, 'handle_subscription_expired'], 10, 1);
        add_action('woocommerce_subscription_status_cancelled', [$this, 'handle_subscription_cancelled'], 10, 1);
        add_action('woocommerce_scheduled_subscription_payment', [$this, 'handle_subscription_renewed'], 10, 1);
        
        // Trial handling
        add_action('woocommerce_checkout_order_processed', [$this, 'handle_trial_start'], 10, 3);
        
        // Admin resync action
        add_action('admin_post_ava_resync_subscriptions', [$this, 'handle_resync_subscriptions']);

        // Email change synchronization
        add_action('profile_update', [$this, 'handle_email_change'], 10, 2);
    }
    
    /**
     * Handle new subscription purchase
     */
    public function handle_purchase_complete($order_id) {
        $order = wc_get_order($order_id);
        if (!$order) return;
        
        if (!$this->order_contains_ava_product($order)) return;
        
        $user = $order->get_user();
        if (!$user) {
            $user = $this->create_wp_user_from_order($order);
        }
        
        if (!$user) return;

        $subscriptions = wcs_get_subscriptions_for_order($order_id);
        $subscription = reset($subscriptions);
        
        $this->notify_ava_backend('user_created', [
            'wpUserId' => $user->ID,
            'email' => $user->user_email,
            'displayName' => $user->display_name,
            'wpOrderId' => $order_id,
            'wpSubscriptionId' => $subscription ? $subscription->get_id() : null,
            'subscriptionStatus' => 'active',
            'plan' => 'basic',
            'startedAt' => $subscription ? $subscription->get_date('start') : current_time('mysql'),
            'expiresAt' => $subscription ? $subscription->get_date('end') : null,
            'isTrial' => false
        ]);
    }

    /**
     * Handle user email change
     */
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
    
    /**
     * Create WordPress user from order (Secure password handling)
     */
    private function create_wp_user_from_order($order) {
        $email = $order->get_billing_email();
        $username = sanitize_user(current(explode('@', $email)));
        $password = wp_generate_password(24, true, true);
        
        $user_id = wp_create_user($username, $password, $email);
        
        if (!is_wp_error($user_id)) {
            wp_update_user([
                'ID' => $user_id,
                'display_name' => $order->get_billing_first_name() . ' ' . $order->get_billing_last_name()
            ]);
            wp_new_user_notification($user_id, null, 'both');
            return get_user_by('id', $user_id);
        }
        return null;
    }
    
    /**
     * Handle trial start
     */
    public function handle_trial_start($order_id, $posted_data, $order) {
        if (!$this->order_contains_ava_product($order)) return;
        
        $subscriptions = wcs_get_subscriptions_for_order($order_id);
        $subscription = reset($subscriptions);
        
        if ($subscription && $subscription->get_trial_period()) {
            $user = $order->get_user();
            if (!$user) return;

            $this->notify_ava_backend('trial_started', [
                'wpUserId' => $user->ID,
                'email' => $user->user_email,
                'displayName' => $user->display_name,
                'wpOrderId' => $order_id,
                'wpSubscriptionId' => $subscription->get_id(),
                'subscriptionStatus' => 'trial',
                'trialEndsAt' => $subscription->get_date('trial_end')
            ]);
        }
    }
    
    /**
     * Handle subscription activated/renewed
     */
    public function handle_subscription_activated($subscription) {
        $this->notify_ava_status_change($subscription, 'subscription_activated', 'active');
    }

    public function handle_subscription_renewed($subscription) {
        $this->notify_ava_status_change($subscription, 'subscription_renewed', 'active');
    }

    /**
     * Handle subscription expiry
     */
    public function handle_subscription_expired($subscription) {
        $this->notify_ava_status_change($subscription, 'subscription_expired', 'expired');
    }
    
    /**
     * Handle subscription cancellation
     */
    public function handle_subscription_cancelled($subscription) {
        $this->notify_ava_status_change($subscription, 'subscription_cancelled', 'cancelled');
    }

    private function notify_ava_status_change($subscription, $eventType, $status) {
        $user = $subscription->get_user();
        if (!$user) return;

        $this->notify_ava_backend($eventType, [
            'wpUserId' => $user->ID,
            'email' => $user->user_email,
            'wpSubscriptionId' => $subscription->get_id(),
            'subscriptionStatus' => $status,
            'timestamp' => current_time('mysql'),
            'expiresAt' => $subscription->get_date('end')
        ]);
    }
    
    /**
     * Handle manual resync
     */
    public function handle_resync_subscriptions() {
        if (!current_user_can('manage_options')) {
            wp_die('Unauthorized');
        }
        
        check_admin_referer('ava_resync_subscriptions');
        
        $count = 0;
        $subscriptions = wcs_get_subscriptions([
            'subscriptions_per_page' => -1,
            'subscription_status' => ['active', 'pending-cancel']
        ]);
        
        foreach ($subscriptions as $subscription) {
            $user = $subscription->get_user();
            if (!$user) continue;
            
            $this->notify_ava_backend('subscription_sync', [
                'wpUserId' => $user->ID,
                'email' => $user->user_email,
                'displayName' => $user->display_name,
                'wpSubscriptionId' => $subscription->get_id(),
                'subscriptionStatus' => $subscription->get_status(),
                'expiresAt' => $subscription->get_date('end')
            ]);
            $count++;
        }
        
        wp_redirect(admin_url('options-general.php?page=ava-embed-settings&resynced=' . $count));
        exit;
    }
    
    /**
     * Send notification to AVA backend
     */
    private function notify_ava_backend($eventType, $data) {
        if (isset($data['email'])) {
            $data['email'] = strtolower($data['email']);
        }
        
        $payload = [
            'eventType' => $eventType,
            'siteId' => $this->site_id,
            'timestamp' => current_time('mysql'),
            'data' => $data
        ];
        
        $response = wp_remote_post($this->ava_backend_url . '/api/webhook/subscription', [
            'headers' => [
                'Content-Type' => 'application/json',
                'X-AVA-API-Key' => $this->api_key,
                'X-AVA-Site-ID' => $this->site_id
            ],
            'body' => json_encode($payload),
            'timeout' => 30
        ]);
        
        if (is_wp_error($response)) {
            error_log('AVA Webhook Error: ' . $response->get_error_message());
        }
    }
    
    /**
     * Check if order/subscription contains AVA product
     */
    private function order_contains_ava_product($order_or_sub) {
        $ava_product_ids = get_option('ava_product_ids', []);
        if (is_string($ava_product_ids)) {
            $ava_product_ids = explode(',', $ava_product_ids);
        }

        foreach ($order_or_sub->get_items() as $item) {
            if (in_array($item->get_product_id(), $ava_product_ids)) {
                return true;
            }
        }
        return false;
    }
}

new AVA_Subscription_Manager();
