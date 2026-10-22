[app]
title = Knack
package.name = knack
package.domain = de.kuschtv
source.dir = .
source.include_exts = py,png,wav,txt,md
source.exclude_dirs = tests,bin,.git,.github,__pycache__
version = 17.0.0
requirements = python3,kivy==2.3.1
orientation = landscape
fullscreen = 1
icon.filename = assets/icon.png
android.permissions = INTERNET
android.api = 36
android.minapi = 26
android.ndk = 29
android.archs = arm64-v8a, armeabi-v7a
android.accept_sdk_license = True
android.private_storage = True
android.enable_androidx = True
android.numeric_version = 17
android.debug_artifact = apk
android.release_artifact = apk
android.logcat_filters = python:D *:S
p4a.branch = develop

[buildozer]
log_level = 2
warn_on_root = 1

