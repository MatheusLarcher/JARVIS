package com.larchertech.jarvis

import android.content.Context

class Prefs(ctx: Context) {
    private val sp = ctx.getSharedPreferences("jarvis", Context.MODE_PRIVATE)

    var serverHost: String
        get() = sp.getString("host", "") ?: ""
        set(v) = sp.edit().putString("host", v.trim()).apply()

    var deviceId: String
        get() = sp.getString("device_id", "") ?: ""
        set(v) = sp.edit().putString("device_id", v.trim()).apply()

    var token: String
        get() = sp.getString("token", "") ?: ""
        set(v) = sp.edit().putString("token", v.trim()).apply()

    var room: String
        get() = sp.getString("room", "") ?: ""
        set(v) = sp.edit().putString("room", v.trim()).apply()

    val configured: Boolean get() = serverHost.isNotEmpty() && deviceId.isNotEmpty() && token.isNotEmpty()
}
