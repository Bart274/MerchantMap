module.exports = function (grunt) {

    const sass = require('sass');
    //require('load-grunt-tasks')(grunt);

    // load plugins as needed instead of up front
    require('jit-grunt')(grunt, {
        unzip: 'grunt-zip'
    })

    var path = require('path')
    var fs = require('fs')

    grunt.initConfig({
        pkg: grunt.file.readJSON('package.json'),

        sass: {
            options: {
                implementation: sass,
                sourceMap: true
            },
            dist: {
                files: {
                    'static/dist/css/app.built.css': 'static/sass/main.scss',
                    'static/dist/css/herds.built.css': 'static/sass/herds.scss',
                    'static/dist/css/ruines.built.css': 'static/sass/ruines.scss',
                    'static/dist/css/mobile.built.css': 'static/sass/mobile.scss'
                }
            }
        },
        eslint: {
            src: ['static/js/*.js', '!static/js/vendor/**/*.js']
        },
        babel: {
            options: {
                sourceMap: true
            },
            dist: {
                files: {
                    'static/dist/js/app.built.js': 'static/js/app.js',
                    'static/dist/js/map.built.js': 'static/js/map.js',
                    'static/dist/js/map.common.built.js': 'static/js/map.common.js',
                    'static/dist/js/herds.built.js': 'static/js/herds.js',
                    'static/dist/js/ruines.built.js': 'static/js/ruines.js',
                    'static/dist/js/label.built.js': 'static/js/label.js',
                    'static/dist/js/mobile.built.js': 'static/js/mobile.js',
                    'static/dist/js/custom.built.js': 'static/js/custom.js',
                    'static/dist/js/vendor/markerclusterer.built.js': 'static/js/vendor/markerclusterer.js',
                    'static/dist/js/serviceWorker.built.js': 'static/js/serviceWorker.js'
                }
            }
        },
        uglify: {
            options: {
                banner: '/*\n <%= pkg.name %> <%= grunt.template.today("yyyy-mm-dd") %> \n*/\n',
                sourceMap: true,
                compress: {
                    unused: false
                }
            },
            build: {
                files: {
                    'static/dist/js/app.min.js': 'static/dist/js/app.built.js',
                    'static/dist/js/map.min.js': 'static/dist/js/map.built.js',
                    'static/dist/js/map.common.min.js': 'static/dist/js/map.common.built.js',
                    'static/dist/js/herds.min.js': 'static/dist/js/herds.built.js',
                    'static/dist/js/ruines.min.js': 'static/dist/js/ruines.built.js',
                    'static/dist/js/label.min.js': 'static/dist/js/label.built.js',
                    'static/dist/js/mobile.min.js': 'static/dist/js/mobile.built.js',
                    'static/dist/js/custom.min.js': 'static/dist/js/custom.built.js',
                    'static/dist/js/vendor/markerclusterer.min.js': 'static/dist/js/vendor/markerclusterer.built.js',
                    'static/dist/js/serviceWorker.min.js': 'static/dist/js/serviceWorker.built.js'
                }
            }
        },
        minjson: {
            build: {
                files: {
                    'static/dist/data/occupier_type.min.json': 'static/data/occupier_type.json',
                    'static/dist/data/mapstyle.min.json': 'static/data/mapstyle.json',
                    'static/dist/data/searchmarkerstyle.min.json': 'static/data/searchmarkerstyle.json'
                }
            }
        },
        clean: {
            build: {
                src: 'static/dist'
            }
        },
        watch: {
            options: {
                interval: 1000,
                spawn: true
            },
            js: {
                files: ['static/js/**/*.js'],
                options: {livereload: true},
                tasks: ['js-lint', 'js-build']
            },
            json: {
                files: ['static/*.json', 'static/data/*.json', 'static/locales/*.json'],
                options: {livereload: true},
                tasks: ['json']
            },
            css: {
                files: '**/*.scss',
                options: {livereload: true},
                tasks: ['css-build']
            }
        },
        cssmin: {
            options: {
                banner: '/*\n <%= pkg.name %> <%= grunt.template.today("yyyy-mm-dd") %> \n*/\n'
            },
            build: {
                files: {
                    'static/dist/css/app.min.css': 'static/dist/css/app.built.css',
                    'static/dist/css/herds.min.css': 'static/dist/css/herds.built.css',
                    'static/dist/css/ruines.min.css': 'static/dist/css/ruines.built.css',
                    'static/dist/css/mobile.min.css': 'static/dist/css/mobile.built.css'
                }
            }
        }

    })

    grunt.registerTask('js-build', ['newer:babel', 'newer:uglify'])
    grunt.registerTask('css-build', ['newer:sass', 'newer:cssmin'])
    grunt.registerTask('js-lint', ['newer:eslint'])
    grunt.registerTask('json', ['newer:minjson'])

    grunt.registerTask('build', ['clean', 'js-build', 'css-build', 'json'])
    grunt.registerTask('lint', ['js-lint'])
    grunt.registerTask('default', ['build', 'watch'])
}
