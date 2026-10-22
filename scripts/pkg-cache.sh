#!/usr/bin/env sh
# Platform pkg-cache helpers (PLATFORM-4517).
# See: platform/docs/src/infrastructure/services/pkg-cache/README.md
#
#   . scripts/pkg-cache.sh
#   pkg_cache_set_defaults
#   pkg_cache_rewrite_apt_ubuntu

pkg_cache_set_defaults() {
	: "${PKG_CACHE_ALPINE:=http://pkg-cache-alpine.iportal.ru}"
	: "${PKG_CACHE_DEBIAN:=http://pkg-cache-debian.iportal.ru}"
	: "${PKG_CACHE_UBUNTU:=http://pkg-cache-ubuntu.iportal.ru}"
	export PKG_CACHE_ALPINE PKG_CACHE_DEBIAN PKG_CACHE_UBUNTU
}

pkg_cache_rewrite_apk_repos() {
	pkg_cache_set_defaults
	[ -f /etc/apk/repositories ] || return 0
	sed -i \
		-e "s|https://dl-cdn.alpinelinux.org|${PKG_CACHE_ALPINE}|g" \
		-e "s|http://dl-cdn.alpinelinux.org|${PKG_CACHE_ALPINE}|g" \
		/etc/apk/repositories
}

pkg_cache_rewrite_apt_debian() {
	pkg_cache_set_defaults
	[ -d /etc/apt ] || return 0
	find /etc/apt -type f \( -name '*.list' -o -name '*.sources' \) \
		-exec sed -i "s|https\\?://deb.debian.org|${PKG_CACHE_DEBIAN}|g" {} +
}

pkg_cache_rewrite_apt_ubuntu() {
	pkg_cache_set_defaults
	[ -d /etc/apt ] || return 0
	find /etc/apt -type f \( -name '*.list' -o -name '*.sources' \) \
		-exec sed -i \
			-e "s|https\\?://archive.ubuntu.com|${PKG_CACHE_UBUNTU}|g" \
			-e "s|https\\?://security.ubuntu.com|${PKG_CACHE_UBUNTU}|g" \
			{} +
}
