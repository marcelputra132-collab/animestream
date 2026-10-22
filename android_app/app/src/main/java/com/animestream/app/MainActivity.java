package com.animestream.app;

import android.annotation.SuppressLint;
import android.app.AlertDialog;
import android.content.Context;
import android.content.SharedPreferences;
import android.content.pm.ActivityInfo;
import android.graphics.Bitmap;
import android.os.Build;
import android.os.Bundle;
import android.view.Gravity;
import android.view.KeyEvent;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowManager;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.ProgressBar;
import android.widget.Toast;
import androidx.activity.OnBackPressedCallback;
import androidx.appcompat.app.AppCompatActivity;

public class MainActivity extends AppCompatActivity {

    private static final String PREFS_NAME = "AnimeStreamPrefs";
    private static final String KEY_SERVER_URL = "server_url";
    private static final String DEFAULT_URL = "https://bronze-dicke-lock-bon.trycloudflare.com";

    private WebView webView;
    private ProgressBar progressBar;
    private FrameLayout customViewContainer;
    private WebChromeClient.CustomViewCallback customViewCallback;
    private View mCustomView;
    private SharedPreferences prefs;
    private long backPressedTime = 0;

    @SuppressLint("SetJavaScriptEnabled")
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        // Hardware acceleration penuh agar video streaming lancar tanpa frame hitam
        getWindow().setFlags(
            WindowManager.LayoutParams.FLAG_HARDWARE_ACCELERATED,
            WindowManager.LayoutParams.FLAG_HARDWARE_ACCELERATED
        );

        setContentView(R.layout.activity_main);

        webView = findViewById(R.id.webView);
        progressBar = findViewById(R.id.progressBar);
        customViewContainer = findViewById(R.id.customViewContainer);
        prefs = getSharedPreferences(PREFS_NAME, MODE_PRIVATE);

        setupWebView();

        // Mencegah aplikasi langsung keluar saat tombol kembali / gesture swipe ditekan
        getOnBackPressedDispatcher().addCallback(this, new OnBackPressedCallback(true) {
            @Override
            public void handleOnBackPressed() {
                handleBackAction();
            }
        });

        String currentUrl = prefs.getString(KEY_SERVER_URL, DEFAULT_URL);
        // Otomatis perbarui jika URL lama adalah domain trycloudflare yang sudah berganti
        if (currentUrl.contains("trycloudflare.com") && !currentUrl.equals(DEFAULT_URL)) {
            currentUrl = DEFAULT_URL;
            prefs.edit().putString(KEY_SERVER_URL, DEFAULT_URL).apply();
        }
        webView.loadUrl(currentUrl);

        // Long click untuk membuka dialog ganti IP / URL server
        webView.setOnLongClickListener(v -> {
            showServerSettingDialog();
            return true;
        });
    }

    @SuppressLint("SetJavaScriptEnabled")
    private void setupWebView() {
        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setDatabaseEnabled(true);
        settings.setAllowFileAccess(true);
        settings.setAllowContentAccess(true);
        settings.setMediaPlaybackRequiresUserGesture(false);
        settings.setLoadWithOverviewMode(true);
        settings.setUseWideViewPort(true);
        settings.setBuiltInZoomControls(false);
        settings.setDisplayZoomControls(false);
        settings.setCacheMode(WebSettings.LOAD_DEFAULT);

        // Keamanan Google Safe Browsing
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            settings.setSafeBrowsingEnabled(true);
        }

        settings.setSupportMultipleWindows(false);
        settings.setJavaScriptCanOpenWindowsAutomatically(false);

        String defaultUa = settings.getUserAgentString();
        settings.setUserAgentString(defaultUa + " AnimeStreamShield/1.0");

        webView.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                String urlStr = request.getUrl().toString().toLowerCase();
                if (urlStr.contains("shopee") || urlStr.contains("lazada") || urlStr.contains("tokopedia") || 
                    urlStr.contains("adsterra") || urlStr.contains("popads") || urlStr.contains("exoclick") ||
                    urlStr.startsWith("intent:") || urlStr.startsWith("market:") || urlStr.endsWith(".apk") || 
                    urlStr.startsWith("tel:") || urlStr.startsWith("sms:")) {
                    return true;
                }
                return false;
            }

            @Override
            public void onPageStarted(WebView view, String url, Bitmap favicon) {
                progressBar.setVisibility(View.VISIBLE);
            }

            @Override
            public void onPageFinished(WebView view, String url) {
                progressBar.setVisibility(View.GONE);
            }

            @Override
            public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                if (request.isForMainFrame()) {
                    progressBar.setVisibility(View.GONE);
                    showConnectionErrorDialog();
                }
            }
        });

        webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onProgressChanged(WebView view, int newProgress) {
                progressBar.setProgress(newProgress);
                if (newProgress >= 100) {
                    progressBar.setVisibility(View.GONE);
                }
            }

            @Override
            public void onShowCustomView(View view, CustomViewCallback callback) {
                showCustomView(view, callback);
            }

            @Override
            public void onHideCustomView() {
                hideCustomView();
            }
        });
    }

    private void showCustomView(View view, WebChromeClient.CustomViewCallback callback) {
        if (mCustomView != null) {
            hideCustomView();
            return;
        }

        mCustomView = view;
        customViewCallback = callback;

        // Kunci ke rotasi Landscape saat video fullscreen
        setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE);

        // PENTING: Jangan gunakan View.GONE pada webView!
        // View.GONE mematikan engine rendering Chromium sehingga video jadi blank hitam.
        // Gunakan View.INVISIBLE agar compositor tetap aktif dan video tayang lancar.
        webView.setVisibility(View.INVISIBLE);

        customViewContainer.removeAllViews();
        customViewContainer.addView(view, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT,
                Gravity.CENTER
        ));
        customViewContainer.setVisibility(View.VISIBLE);

        // Layar penuh immersive (sembunyikan status bar & bar navigasi)
        View decorView = getWindow().getDecorView();
        decorView.setSystemUiVisibility(
                View.SYSTEM_UI_FLAG_FULLSCREEN
                        | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                        | View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
                        | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
                        | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
                        | View.SYSTEM_UI_FLAG_LAYOUT_STABLE
        );
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
    }

    private void hideCustomView() {
        if (mCustomView == null) return;

        // Kembalikan orientasi layar
        setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_UNSPECIFIED);

        customViewContainer.removeAllViews();
        customViewContainer.setVisibility(View.GONE);
        webView.setVisibility(View.VISIBLE);

        if (customViewCallback != null) {
            try {
                customViewCallback.onCustomViewHidden();
            } catch (Exception ignored) {}
        }
        mCustomView = null;
        customViewCallback = null;

        // Kembalikan UI sistem normal
        View decorView = getWindow().getDecorView();
        decorView.setSystemUiVisibility(View.SYSTEM_UI_FLAG_VISIBLE);
        getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
    }

    private void handleBackAction() {
        // 1. Jika video sedang dalam mode Fullscreen / Landscape, keluar dari mode fullscreen terlebih dahulu
        if (mCustomView != null) {
            hideCustomView();
            return;
        }

        // 2. Evaluasi apakah ada elemen HTML5 fullscreen aktif di webView
        webView.evaluateJavascript(
            "(function() { if (document.fullscreenElement || document.webkitFullscreenElement) { document.exitFullscreen ? document.exitFullscreen() : (document.webkitExitFullscreen && document.webkitExitFullscreen()); return true; } return false; })()",
            value -> {
                if ("true".equalsIgnoreCase(value)) {
                    return;
                }
                navigateBackOrHome();
            }
        );
    }

    private void navigateBackOrHome() {
        // 3. Jika riwayat webView bisa kembali ke halaman sebelumnya
        if (webView.canGoBack()) {
            webView.goBack();
            return;
        }

        // 4. Jika tidak ada history tapi sedang di sub-halaman (player.html, detail.html, search.html, dll), kembalikan ke Beranda
        String currentUrl = webView.getUrl();
        if (currentUrl != null && !isHomePage(currentUrl)) {
            String homeUrl = prefs.getString(KEY_SERVER_URL, DEFAULT_URL);
            webView.loadUrl(homeUrl);
            return;
        }

        // 5. Jika sudah berada di Beranda (Home), gunakan konfirmasi double back (tekan 2 kali) agar tidak keluar mendadak
        if (backPressedTime + 2000 > System.currentTimeMillis()) {
            finish();
        } else {
            Toast.makeText(this, "Tekan sekali lagi untuk keluar dari aplikasi", Toast.LENGTH_SHORT).show();
            backPressedTime = System.currentTimeMillis();
        }
    }

    private boolean isHomePage(String url) {
        if (url == null) return true;
        String clean = url.split("\\?")[0].split("#")[0];
        return clean.endsWith("/") || clean.endsWith("index.html") || clean.equals(DEFAULT_URL);
    }

    private void showServerSettingDialog() {
        AlertDialog.Builder builder = new AlertDialog.Builder(this);
        builder.setTitle("Pengaturan Alamat Server");
        builder.setMessage("Masukkan alamat server Otakux (Laptop/PC):");

        final EditText input = new EditText(this);
        input.setText(prefs.getString(KEY_SERVER_URL, DEFAULT_URL));
        input.setSelection(input.getText().length());
        builder.setView(input);

        builder.setPositiveButton("Simpan & Muat", (dialog, which) -> {
            String newUrl = input.getText().toString().trim();
            if (!newUrl.isEmpty()) {
                if (!newUrl.startsWith("http://") && !newUrl.startsWith("https://")) {
                    newUrl = "http://" + newUrl;
                }
                prefs.edit().putString(KEY_SERVER_URL, newUrl).apply();
                webView.loadUrl(newUrl);
                Toast.makeText(MainActivity.this, "Alamat disimpan: " + newUrl, Toast.LENGTH_SHORT).show();
            }
        });

        builder.setNegativeButton("Batal", (dialog, which) -> dialog.cancel());
        builder.show();
    }

    private void showConnectionErrorDialog() {
        String currentUrl = prefs.getString(KEY_SERVER_URL, DEFAULT_URL);
        new AlertDialog.Builder(this)
                .setTitle("Tidak Dapat Terhubung")
                .setMessage("Gagal terhubung ke:\n" + currentUrl +
                        "\n\nServer baru yang aktif:\n" + DEFAULT_URL +
                        "\n\nApakah Anda ingin langsung beralih ke server baru?")
                .setPositiveButton("Gunakan Server Baru", (dialog, which) -> {
                    prefs.edit().putString(KEY_SERVER_URL, DEFAULT_URL).apply();
                    webView.loadUrl(DEFAULT_URL);
                })
                .setNeutralButton("Ubah URL Manual", (dialog, which) -> showServerSettingDialog())
                .setNegativeButton("Coba Lagi", (dialog, which) -> webView.reload())
                .show();
    }

    @Override
    public boolean onKeyDown(int keyCode, KeyEvent event) {
        if (keyCode == KeyEvent.KEYCODE_BACK) {
            handleBackAction();
            return true;
        }
        return super.onKeyDown(keyCode, event);
    }

    @Override
    public void onBackPressed() {
        handleBackAction();
    }
}
