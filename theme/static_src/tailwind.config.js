module.exports = {
    content: [
        '../../templates/*.html',
        '../../templates/**/*.html', 
        '../../main/src/index-main.js',
        '../../**/templates/*.html',  
        '!../../**/node_modules',
        /* JS 1: Ignore any JavaScript in node_modules folder. */
        // '!../../**/node_modules',
        /* JS 2: Process all JavaScript files in the project. */
        // '../../**/*.js',
        // '../../**/*.py'
    ],
    theme: {
        extend: {
            colors: {
                'primary': '#1f8e43',
                'secondary': '#FF4444',
                'error': '#E64444',
                'warning': '#FACC15',
                'precio300': '#ffff00',
                'precio350': '#fba657',
                'precio400': '#4ade80',
                'precio450': '#52b551',
                'precio500': '#ff0000',
                'precio600': '#00ffff',
                'precio700': '#50dbff',
                'precio800': '#5eb9fc',
                'precio900': '#6199ee',
                'precio1000': '#808080',
                'precioNegro': 'black'
            },
            fontFamily: {
                'roboto': ['"Roboto"', 'sans-serif']
            },
            // backgroundImage: {
            //   'fondoscz': "url('./static/img/fotoCristo1.webp')",
            //   'fondosvg': "url('./static/img/fotoCristo2.svg')",
            // },
            height: {
                'screen80': '80vh',
                'screen90': '90vh',
            },
            animation: {
                "bounce-bottom": "bounce-bottom 4s ease 2s infinite both",
                "titulo": "titulo 0.5s cubic-bezier(0.250, 0.460, 0.450, 0.940) 2s  both",
                "wapp": "wapp 2s cubic-bezier(0.075, 0.820, 0.165, 1.000)   both"
            },
            keyframes: {
                "wapp": {
                    "0%": {
                        transform: "translateY(-1000px)",
                        opacity: "0"
                    },
                    to: {
                        transform: "translateY(0)",
                        opacity: "1"
                    }
                },
                "titulo": {
                    "0%": {
                        transform: "scale(0)",
                        opacity: "0"
                    },
                    to: {
                        transform: "scale(1)",
                        transform: "translate(-50%, 0)",
                        opacity: "1"
                    }
                },
                "bounce-bottom": {
                    "0%": {},
                    "40%": {
                        transform: "translateY(24px)",
                        "animation-timing-function": "ease-in"
                    },
                    "65%": {
                        transform: "translateY(12px)",
                        "animation-timing-function": "ease-in"
                    },
                    "82%": {
                        transform: "translateY(6px)",
                        "animation-timing-function": "ease-in"
                    },
                    "93%": {
                        transform: "translateY(4px)",
                        "animation-timing-function": "ease-in"
                    },
                    "25%,55%,75%,87%": {
                        transform: "translateY(0)",
                        "animation-timing-function": "ease-out"
                    },
                    to: {
                        transform: "translateY(0)",
                        "animation-timing-function": "ease-out",

                    }
                }
            }
        },
    },
    plugins: [
        /**
         * '@tailwindcss/forms' is the forms plugin that provides a minimal styling
         * for forms. If you don't like it or have own styling for forms,
         * comment the line below to disable '@tailwindcss/forms'.
         */
        require('@tailwindcss/forms'),
        require('@tailwindcss/typography'),
        require('@tailwindcss/aspect-ratio'),
    ],
}
