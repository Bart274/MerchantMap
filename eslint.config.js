const js = require('@eslint/js')
const globals = require('globals')

module.exports = [
    js.configs.recommended,
    {
        files: ['static/js/**/*.js'],
        ignores: ['static/js/vendor/**', 'static/dist/**'],
        languageOptions: {
            ecmaVersion: 2022,
            sourceType: 'script',
            globals: {
                ...globals.browser,
                google: 'readonly',
                L: 'readonly',
                $: 'readonly',
                jQuery: 'readonly',
                moment: 'readonly',
                Push: 'readonly',
                toastr: 'readonly',
                swal: 'readonly',
                randomColor: 'readonly',
                jsts: 'readonly',
                MarkerClusterer: 'readonly',
                mapProvider: 'readonly'
            }
        },
        rules: {
            indent: ['error', 4],
            quotes: ['error', 'single'],
            semi: ['error', 'never'],
            'no-unused-vars': 'warn'
        }
    }
]
