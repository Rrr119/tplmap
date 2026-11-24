<?php
/*
 * Local Twig SSTI range for tplmap detection benchmarks.
 *
 * Contract (mirrors tests/env_php_tests/twig-1.19.0-unsecured.php):
 *
 *   php -S 127.0.0.1:15012 router.php
 *   GET /reflect/twig?tpl=<template with %%s>&inj=<injection>
 *
 * Paths containing filter_canonical enable a tiny denylist that blocks the
 * stock canonical nl2br probe while arithmetic/string payload variants work.
 */

require_once __DIR__ . '/vendor/autoload.php';

use Twig\Environment;
use Twig\Loader\ArrayLoader;

function twig_range_handle(): void
{
    $path = parse_url($_SERVER['REQUEST_URI'] ?? '/', PHP_URL_PATH) ?: '/';

    if (rtrim($path, '/') === '/health') {
        header('Content-Type: text/plain; charset=utf-8');
        echo 'ok';
        return;
    }

    $inj = isset($_GET['inj']) ? (string) $_GET['inj'] : '';
    $tpl = isset($_GET['tpl']) && $_GET['tpl'] !== '' ? (string) $_GET['tpl'] : '%s';

    // filter_canonical blocks the stock nl2br probe; filter_secondary blocks
    // double-quoted literals used by the canonical probe.
    $filters = [
        'filter_canonical' => function (string $value): bool {
            return stripos($value, 'nl2br') !== false;
        },
        'filter_secondary' => function (string $value): bool {
            return strpos($value, '"') !== false;
        },
    ];

    foreach ($filters as $filterName => $isBlocked) {
        if (strpos($path, $filterName) !== false && $isBlocked($inj)) {
            header('Content-Type: text/plain; charset=utf-8');
            echo 'REQUEST BLOCKED BY RANGE FILTER';
            return;
        }
    }

    // Keep the formatting a-la-python: replace the %s placeholder.
    $source = str_replace('%s', $inj, $tpl);

    try {
        $loader = new ArrayLoader(['tpl' => $source]);
        $twig = new Environment($loader, [
            'debug' => false,
            'cache' => false,
            'autoescape' => false,
        ]);
        $rendered = $twig->render('tpl');
        header('Content-Type: text/plain; charset=utf-8');
        echo $rendered;
    } catch (\Throwable $e) {
        // Broken/blocked templates render nothing, like the upstream range.
        header('Content-Type: text/plain; charset=utf-8');
        echo '';
    }
}

twig_range_handle();
